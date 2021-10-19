import datetime
import json

import requests

from flask import Flask, request, jsonify, render_template
from flask_marshmallow import Marshmallow
from flask_marshmallow.fields import fields
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from marshmallow import INCLUDE
from marshmallow_sqlalchemy.fields import Nested
from sqlalchemy import desc, asc, and_
from sqlalchemy.sql.elements import or_

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

    @classmethod
    def find_by_name(cls, name):
        return cls.query.filter_by(name=name).first()

    @classmethod
    def find_or_create(cls, name):
        existed_author = cls.find_by_name(name)
        if existed_author:
            author = existed_author
        else:
            author = cls(name=name)
            db.session.add(author)
            db.session.commit()
        return author

    def __repr__(self):
        return f"Author:{self.name}, Books: {[book.title for book in self.books]}"


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(), nullable=False)
    books = db.relationship('Book', secondary=categories, lazy='subquery',
                            backref=db.backref('categories', lazy=True))

    @classmethod
    def find_by_type(cls, type):
        return cls.query.filter_by(type=type).first()

    @classmethod
    def find_or_create(cls, book_type):
        existed_category = Category.find_by_type(book_type)
        if existed_category:
            category = existed_category
        else:
            category = cls(type=book_type)
            db.session.add(category)
            db.session.commit()
        return category

    def __repr__(self):
        return f"Category:{self.type}"


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    googlebooks_api_id = db.Column(db.String(70), nullable=False, unique=True)
    title = db.Column(db.String(), nullable=False)
    published_date = db.Column(db.String(20))
    average_rating = db.Column(db.Integer)
    ratings_count = db.Column(db.Integer)
    thumbnail = db.Column(db.String(120))
    authors = db.relationship('Author', secondary=authors, lazy='subquery',
                              backref=db.backref('books', lazy=True))

    def __repr__(self):
        return f"Title: {self.title}|Authors {self.authors} | published_date: {self.published_date}| categories: {self.categories} | average_rating: {self.average_rating} | ratings_count: {self.ratings_count} | thumbnail: {self.thumbnail}"

    @classmethod
    def find_book(cls, gb_api_id=None):
        return cls.query.filter_by(googlebooks_api_id=gb_api_id).first()

    @classmethod
    def order_by_published_date(cls, sort_parm):
        filed_sortby = sort_parm.lstrip('-+')
        result = cls.query.order_by(desc(filed_sortby)).all()
        if sort_parm.startswith('-'):
            result = cls.query.order_by(asc(filed_sortby)).all()
        return result

    @classmethod
    def filter_by_authors(cls, auhtors_list):
        # https://stackoverflow.com/questions/66373427/how-do-i-pass-multiple-parameters-from-list-in-sqlalchemy-filter-statement
        # result=Book.query.filter(or_(*[Book.authors.any(Author.name.contains(name)) for name in authors_list])).all()
        result = Book.query.filter((Book.authors.any(Author.name.in_(auhtors_list)))).all()
        return result


class BookSchema(ma.SQLAlchemyAutoSchema):
    authors = fields.List(fields.Nested(lambda: AuthorSchema(only=("name",))))
    categories = fields.List(fields.Nested(lambda: CategorySchema(only=("type",))))

    class Meta:
        model = Book
        load_instance = True
        include_relationships = True


class AuthorSchema(ma.SQLAlchemyAutoSchema):
    books = fields.List(fields.Nested(BookSchema(exclude=("authors",))))

    class Meta:
        model = Author
        load_instance = True
        include_relationships = True


class CategorySchema(ma.SQLAlchemyAutoSchema):
    books = fields.List(fields.Nested(BookSchema(exclude=("categories",))))

    class Meta:
        model = Category
        load_instance = True
        include_relationships = True


book_schema = BookSchema(exclude=("googlebooks_api_id", "id",))
books_schema = BookSchema(many=True)

category_schema = CategorySchema()
categories_schema = CategorySchema(many=True)


class GoogleBookApiList(Resource):
    def get(self):
        books_db = Book.query.all()
        sort_q = request.args.get('sort')
        published_q = request.args.get("published_date")
        authors_q = request.args.getlist("author")
        if sort_q:
            books_db = Book.order_by_published_date(sort_q)
        elif published_q:
            books_db = Book.query.filter(Book.published_date.contains(published_q)).all()
        elif authors_q:
            books_db = Book.filter_by_authors(authors_q)
        if not books_db:
            return {"message": f"No result for such criteria: {[request.args.get(key) for key in request.args]}"}, 400
        return books_schema.dump(books_db)




class GoogleBookApiBook(Resource):
    def get(self, id):
        book_db = Book.query.get_or_404(id, description="Book Not found,please check the id")
        return book_schema.dump(book_db), 200


class GoogleBookApiLoad(Resource):
    def post(self):

        data = request.get_json()
        if not data:
            return {"message": "No input data provided"}, 400
        gb_volume_search = data.get('gb_volume')
        googleapis_booklist_json = requests.get(
            f"https://www.googleapis.com/books/v1/volumes?q={gb_volume_search}").json()
        googleapis_booklist = [books_items for books_items in googleapis_booklist_json["items"]]
        books_to_db = []
        for book_data in googleapis_booklist:
            existed_book = Book.find_book(book_data.get('id'))
            categories_list = [Category.find_or_create(book_type=ctgry_type) for ctgry_type in
                               book_data.get('volumeInfo').get('categories', [])]
            authors_list = [Author.find_or_create(name=auth_name) for auth_name in
                            book_data.get('volumeInfo').get('authors', [])]
            if existed_book:
                existed_book.title = book_data.get('volumeInfo').get('title', existed_book.title)
                existed_book.published_date = book_data.get('volumeInfo').get('publishedDate',
                                                                              existed_book.published_date)
                existed_book.thumbnail = book_data.get('volumeInfo').get('imageLinks', {}).get("thumbnail",
                                                                                               existed_book.thumbnail)
                existed_book.average_rating = book_data.get('volumeInfo').get("averageRating",
                                                                              existed_book.average_rating)
                existed_book.ratings_count = book_data.get('volumeInfo').get("ratingsCount", existed_book.ratings_count)
                existed_book.authors = authors_list if authors_list else existed_book.authors
                existed_book.categories = categories_list if categories_list else existed_book.categories
                books_to_db.append(existed_book)
            else:
                new_book = Book(googlebooks_api_id=book_data.get('id'), title=book_data.get('volumeInfo').get('title'),
                                published_date=book_data.get('volumeInfo').get('publishedDate'),
                                thumbnail=book_data.get('volumeInfo').get('imageLinks', {}).get("thumbnail"),
                                average_rating=book_data.get('volumeInfo').get("averageRating"),
                                ratings_count=book_data.get('volumeInfo').get("ratingsCount")
                                )
                new_book.authors.extend(authors_list)
                new_book.categories.extend(categories_list)
                books_to_db.append(new_book)
        try:
            db.session.add_all(books_to_db)
            db.session.commit()
        except Exception as exc:
            return {"message": exc}, 400
        return books_schema.dump(books_to_db)


api.add_resource(GoogleBookApiBook, '/api/books/<int:id>', endpoint="booksid")
api.add_resource(GoogleBookApiList, '/api/', '/books', endpoint="books")
api.add_resource(GoogleBookApiLoad, '/api/db', endpoint='to_db')


@app.route('/home', methods=['GET', 'POST'])
@app.route('/', methods=['GET', 'POST'])
def home():
    return render_template("layout.html")


@app.cli.command("initdb")
def reset_db():
    """Drops and Creates fresh database"""
    db.drop_all()
    db.create_all()
    print("Initialized default DB")


@app.cli.command("bootstrap")
def bootstrap_data():
    """Populates database with data"""


    """testdata"""

    db.session.commit()

    print("Added development dataset")


if __name__ == '__main__':
    app.run()
