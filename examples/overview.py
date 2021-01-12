from dataclasses import dataclass
from datetime import date, datetime
from typing import Collection, Optional
from uuid import UUID, uuid4

from graphql import graphql_sync, print_schema

from apischema.graphql import graphql_schema, resolver


@dataclass
class User:
    id: UUID
    username: str
    birthday: Optional[date] = None

    @resolver
    def posts(self) -> Collection["Post"]:
        return [post for post in POSTS if post.author.id == self.id]


@dataclass
class Post:
    id: UUID
    author: User
    date: datetime
    content: str


USERS = [User(uuid4(), "foo"), User(uuid4(), "bar")]
POSTS = [Post(uuid4(), USERS[0], datetime.now(), "Hello world!")]


def users() -> Collection[User]:
    return USERS


def posts() -> Collection[Post]:
    return POSTS


def user(username: str) -> Optional[User]:
    for user in users():
        if user.username == username:
            return user
    else:
        return None


schema = graphql_schema(query=[users, user, posts], id_types={UUID})
schema_str = """\
type Query {
  users: [User!]!
  user(username: String!): User
  posts: [Post!]!
}

type User {
  id: ID!
  username: String!
  birthday: Date
  posts: [Post!]!
}

scalar Date

type Post {
  id: ID!
  author: User!
  date: Datetime!
  content: String!
}

scalar Datetime
"""
assert print_schema(schema) == schema_str

query = """
{
  users {
    username
    posts {
        content
    }
  }
}
"""
assert graphql_sync(schema, query).data == {
    "users": [
        {"username": "foo", "posts": [{"content": "Hello world!"}]},
        {"username": "bar", "posts": []},
    ]
}
