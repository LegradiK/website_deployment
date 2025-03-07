import os
from datetime import date
from typing import List
from flask import Flask, request, abort, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
# Import your forms from the forms.py
from forms import CreatePostForm, RegistrationForm, LoginForm, CommentForm


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_KEY')
ckeditor = CKEditor(app)
Bootstrap5(app)
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)
# Make Gravatar globally available in Jinja templates
app.jinja_env.globals['gravatar'] = gravatar

# TODO: Configure Flask-Login


# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URL')
db = SQLAlchemy(model_class=Base)
db.init_app(app)


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    parent_user: Mapped["User"] = relationship("User", back_populates="user_comments", foreign_keys=[parent_user_id])
    parent_posts_id: Mapped[int] = mapped_column(ForeignKey("blogs.id"))
    parent_posts: Mapped["BlogPost"] = relationship("BlogPost", back_populates="blog_comments", foreign_keys=[parent_posts_id])
    comment: Mapped[str] = mapped_column(Text, nullable=False)

# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blogs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    parent: Mapped["User"] = relationship("User", back_populates="blog_posts", foreign_keys=[parent_id])
    blog_comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="parent_posts", foreign_keys=[Comment.parent_posts_id])
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)

# TODO: Create a User table for all your registered users.
class User(db.Model, UserMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blog_posts: Mapped[List["BlogPost"]] = relationship("BlogPost", back_populates="parent", foreign_keys=[BlogPost.parent_id])
    user_comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="parent_user", foreign_keys=[Comment.parent_user_id])
    email: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(250), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)



with app.app_context():
    db.create_all()

login_manager = LoginManager()
login_manager.init_app(app)

def admin_only(func):
    @wraps(func)
    def decorated_function(*args,**kwargs):
        if current_user.is_authenticated and current_user.id == 1:
            return func(*args, **kwargs)
        else:
            abort(403)
    return decorated_function


# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=['GET','POST'])
def register():
    registration_form = RegistrationForm()
    login_email = registration_form.email.data
    if db.session.query(User).filter(User.email == login_email).first():
        flash("This email is already registered. Please login instead.", category="error")
        return redirect(url_for('login'))

    if registration_form.validate_on_submit():
        password = registration_form.password.data
        new_user = User(
        email = login_email,
        password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8),
        name = registration_form.name.data
        )
        db.session.add(new_user)
        db.session.commit()
        flash("You've registered successfully!", "info")
        login_user(new_user, remember=True)
        user_data = db.session.execute(db.select(User).where(User.email == new_user.email)).scalar_one_or_none()
        return redirect(url_for('get_all_posts', logged_in=True, id=user_data.id))
    return render_template("register.html", form=registration_form)

# get user details
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# TODO: Retrieve a user from the database based on their email.
@app.route('/login', methods=['GET','POST'])
def login():
    login_form = LoginForm()
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user_data = db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none()
        if user_data == None:
            flash("This email doesn't exist in the database. Please register first.", category="error")
            return redirect(url_for('register'))

        if check_password_hash(user_data.password,password):
            login_user(user_data, remember=True)
            flash("Login successful :)", category="info")
            user_id = user_data.id
            return redirect(url_for('get_all_posts', logged_in=True, id=user_id))
        else:
            flash("Wrong password. Please try again.", category="error")
            return redirect(url_for('login'))
    return render_template("login.html", form=login_form)


@app.route('/logout')
def logout():
    logout_user()
    flash("Logout successfully", "info")
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    if current_user.is_authenticated:
        return render_template("index.html", all_posts=posts,
                               logged_in=current_user.is_authenticated,  # Ensures `logged_in` is always passed
                               id=current_user.id if current_user.is_authenticated else None)  # Pass `id` only if logged in
    return render_template("index.html", all_posts=posts)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=['GET','POST'])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    post_commments = db.session.execute(db.select(Comment).where(Comment.parent_posts_id == post_id)).scalars().all()
    if current_user.is_authenticated:
        if comment_form.validate_on_submit():
            new_comment = Comment(
                    comment = comment_form.comment.data,
                    parent_user = current_user,
                    parent_posts = requested_post
                )
            db.session.add(new_comment)
            db.session.commit()
            flash("Your comment has been successfully saved", "info")
            return redirect(url_for('show_post', post_id=post_id))
        elif not current_user.is_authenticated:
            flash("You need to log in to comment.", "error")
            return redirect(url_for("login"))
        return render_template("post.html", post=requested_post, form=comment_form, logged_in=True, id=current_user.id, comments=post_commments)

    return render_template("post.html", post=requested_post, comments=post_commments)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            parent=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, logged_in=True)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        parent=post.parent,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.parent = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, logged_in=True)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


if __name__ == "__main__":
    app.run(debug=True, port=5002)
