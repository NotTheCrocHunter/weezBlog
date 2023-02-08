import flask
from flask import Flask, render_template, request, url_for, redirect, session, flash, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
import smtplib
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor, CKEditorField
from datetime import datetime
from forms import RegisterForm, CreatePostForm, LoginForm, CommentForm
from functools import wraps
from sqlalchemy.orm import relationship
from flask_gravatar import Gravatar
import os

# Get current year to add to footer
CURRENT_YEAR = datetime.now().year
OWN_EMAIL = os.environ['EMAIL']
OWN_PASSWORD = os.environ['OWN_PASSWORD']
test = 'test'

SALT_LENGTH = 8
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ['SECRET_KEY']

# Run app through various classes
ckeditor = CKEditor(app)
Bootstrap(app)
gravatar = Gravatar(app, size=100, rating='g', default='retro', force_default=False, force_lower=False, use_ssl=False, base_url=None)

# CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URL', 'sqlite:///blog.db')  # 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)



#############
# Flask Login
#############
# create LoginManager class configure the app for login
login_manager = LoginManager()
login_manager.init_app(app)


# provide user_loader callback
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Create admin-only decorator
def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # If id is not 1 then return abort with 403 error
        if current_user.is_anonymous or current_user.id != 1:
            return abort(403)
        # Otherwise, continue with the route function
        return f(*args, **kwargs)
    return decorated_function


# CONFIGURE TABLE
class BlogPost(db.Model):
    __tablename__ = 'blog_posts'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.Date(), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)

    # Create the Foreign Key - the users refers to the tablename of User
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Create reference to the User object, the "posts" refers to the post's property in the User class.
    author = db.relationship('User', back_populates="posts")
    comments = db.relationship("Comment", back_populates="parent_post")


# CREATE TABLE IN DB
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))

    # This will act like a List of BlogPost objects attached to each User
    # The "author" refers to the author property in the BlogPost class.
    # relation link to one to many: one author many blog_posts
    posts = db.relationship("BlogPost", back_populates='author')

    # "comment_author" refers to the comment_author property in the Comment class.
    comments = db.relationship("Comment", back_populates="comment_author")


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"))
    # *******Add child relationship*******#
    # "users.id" The users refers to the tablename of the Users class.
    # "comments" refers to the comments property in the User class.
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    comment_author = db.relationship("User", back_populates="comments")
    parent_post = db.relationship("BlogPost", back_populates="comments")


# Functions to serve up pages
@app.route('/')  # Decorator that reads/routes traffic based on the url/directory
def home():
    # Why does this need to be with app.app_context()
    # with app.app_context():
    db.create_all()
    blog_posts = db.session.query(BlogPost).order_by(BlogPost.date.desc()).all()
    print(blog_posts)
    print('stop')
    return render_template("index.html", all_posts=blog_posts, year=CURRENT_YEAR, current_user=current_user)


@app.route("/post/<int:post_id>", methods=['GET', 'POST'])
def show_post(post_id):
    form = CommentForm()
    requested_post = BlogPost.query.get(post_id)

    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.")
            return redirect(url_for("login"))

        new_comment = Comment(
            text=form.comment_text.data,
            comment_author=current_user,
            parent_post=requested_post
        )
        db.session.add(new_comment)
        db.session.commit()
    return render_template("post.html", post=requested_post, current_user=current_user, form=form)


@app.route('/about')
def about():
    return render_template("about.html")


@app.route('/contact', methods=["GET", "POST"])
def contact():
    # First function using POST method
    if request.method == "POST":
        data = request.form
        send_email(data["name"], data["email"], data["phone"], data["message"])
        return render_template("contact.html", msg_sent=True)
    return render_template("contact.html", msg_sent=False)


def send_email(name, email, phone, message):
    email_message = f"Subject:New Message\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nMessage:{message}"
    with smtplib.SMTP("smtp.mail.yahoo.com", port=587) as connection:
        connection.starttls()
        connection.login(OWN_EMAIL, OWN_PASSWORD)
        connection.sendmail(OWN_EMAIL, OWN_EMAIL, email_message)


@app.route('/new-post', methods=['GET', 'POST'])
@admin_only
def create_new_post():

    form = CreatePostForm(date=datetime.today().date())

    if form.validate_on_submit():
        # Get blog text and create new db item
        new_post = BlogPost(
            author=current_user,
            title=form.title.data,
            subtitle=form.subtitle.data,
            img_url=form.img_url.data,
            body=form.body.data,
            date=form.date.data
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('make-post.html', form=form)


# Once a user has authenticated, log them in with the login_user function
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        # Find user by email entered.
        email = form.email.data
        user = User.query.filter_by(email=email).first()

        # Get password data from form
        password = form.password.data

        # Email doesn't exist
        if not user:
            flash('That email does not exist')
            return redirect(url_for('login'))
        # Check stored password has against entered password hashed.
        elif not check_password_hash(user.password, password):
            flash('Incorrect password')
            return redirect(url_for('login'))
        # Email exists and password matches
        else:
            login_user(user)
            session['user_name'] = user.name
            return redirect(url_for('home', name=session['user_name']))

    return render_template("login.html", form=form, logged_in=current_user.is_authenticated)


# Log out user
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/register', methods=['GET', 'POST'])
def register_new_user():
    form = RegisterForm()

    if form.validate_on_submit():

        hash_and_salted_password = generate_password_hash(
            form.password.data,
            method='pbkdf2:sha256',
            salt_length=SALT_LENGTH
        )

        new_user = User(
            email=form.email.data,
            name=form.name.data,
            password=hash_and_salted_password
        )

        session['user_name'] = new_user.name
        db.session.add(new_user)
        db.session.commit()

        # Log in and authenticate user after adding details to database
        login_user(new_user)
        return redirect(url_for('home', name=session['user_name']))

    return render_template('register.html', form=form)


@app.route('/edit-post/<post_id>', methods=['GET', 'POST'])
@admin_only
def edit_post(post_id):
    post = BlogPost.query.get(post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body,
        date=post.date
    )

    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = edit_form.author.data
        post.body = edit_form.body.data
        post.date = edit_form.date.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = BlogPost.query.get(post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('home'))


if __name__ == "__main__":
    app.run(debug=True)
