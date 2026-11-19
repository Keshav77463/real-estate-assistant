import os, psycopg
from pgvector.psycopg import register_vector

def conn():
    c = psycopg.connect(os.environ['DATABASE_URL'])
    register_vector(c)
    return c
