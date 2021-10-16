import datetime
import json

import requests

from flask import Flask, request
from flask_marshmallow import Marshmallow
from flask_marshmallow.fields import fields
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from marshmallow import INCLUDE
from marshmallow_sqlalchemy.fields import Nested

import config

app = Flask(__name__)
if app.config['ENV'] == 'development':
    app.config.from_object(config.Config)
else:
    app.config.from_object(config.ConfigProd)

db = SQLAlchemy(app)
ma = Marshmallow(app)
api = Api(app)

authors = db.Table('authors',
                   db.Column('author_id', db.Integer, db.ForeignKey('author.id'), primary_key=True),
                   db.Column('book_id', db.Integer, db.ForeignKey('book.id'), primary_key=True)
                   )
categories = db.Table('categories',
                      db.Column('book_id', db.Integer, db.ForeignKey('book.id'), primary_key=True),
                      db.Column('category_id', db.Integer, db.ForeignKey('category.id'), primary_key=True)
                      )


class Author(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(), nullable=False)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(), nullable=False)
    books = db.relationship('Book', secondary=categories, lazy='subquery',
                            backref=db.backref('categories', lazy=True))


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(), nullable=False)
    published_date = db.Column(db.String(4))
    average_rating = db.Column(db.Integer)
    ratings_count = db.Column(db.Integer)
    thumbnail = db.Column(db.String(120))
    authors = db.relationship('Author', secondary=authors, lazy='subquery',
                              backref=db.backref('books', lazy=True))

    def __repr__(self):
        return f"Title: {self.title}|Authors '' | published_date: {self.published_date}| categories: {self.categories} | average_rating: {self.average_rating} | ratings_count: {self.ratings_count} | thumbnail: {self.thumbnail}"


class BookSchema(ma.SQLAlchemyAutoSchema):
    authors = fields.List(fields.Nested(lambda: AuthorSchema(only=("name",))))
    categories = fields.List(fields.Nested(lambda: CategorySchema(only=("type",))))

    class Meta:
        model = Book
        load_instance = True
        include_relationships = True
        # fields = ('title', "published_date", 'authors', 'categories')


class AuthorSchema(ma.SQLAlchemyAutoSchema):
    books = fields.List(fields.Nested(BookSchema(exclude=("authors",))))

    class Meta:
        model = Author
        load_instance = True
        include_relationships = True
        # fields = ('name',)


class CategorySchema(ma.SQLAlchemyAutoSchema):
    books = fields.List(fields.Nested(BookSchema(exclude=("categories",))))

    class Meta:
        model = Category
        load_instance = True
        include_relationships = True


book_schema = BookSchema()
books_schema = BookSchema(many=True)

category_schema = CategorySchema()
categories_schema = CategorySchema(many=True)


class BookApiList(Resource):
    def get(self):
        # googleapis_booklist_json = requests.get("https://www.googleapis.com/books/v1/volumes?q=Hobbit").json()
        # googleapis_booklist = [i["volumeInfo"] for i in googleapis_booklist_json["items"]]
        #
        # return googleapis_booklist
        books_db = Book.query.all()
        return books_schema.dump(books_db)

    def post(self):
        data = request.get_json()
        if not data:
            return {"message": "No input data provided"}, 400
        new_book=book_schema.load(data)

        db.session.add(new_book)
        db.session.commit()
        return book_schema.jsonify(new_book)


api.add_resource(BookApiList, '/', '/home')


@app.cli.command("initdb")
def reset_db():
    """Drops and Creates fresh database"""
    db.drop_all()
    db.create_all()
    print("Initialized default DB")


@app.cli.command("bootstrap")
def bootstrap_data():
    """Populates database with data"""
    db.drop_all()
    db.create_all()

    boo = Book(title='Cos', published_date=2015)
    db.session.add(boo)
    au = Author(name='Fagot')
    boo.authors.append(au)
    db.session.add(au)

    cat = Category(type='Computers')
    db.session.add(cat)
    boo.categories.append(cat)

    db.session.commit()

    print("Added development dataset")


if __name__ == '__main__':
    app.run()
