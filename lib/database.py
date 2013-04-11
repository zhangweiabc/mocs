from sqlalchemy import create_engine, Column, Integer, Boolean, UnicodeText, Table, ForeignKey, func
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.declarative import _declarative_constructor
from mocs_config import SQL_CONNECTION
from re import sub, compile

### configuration ###
echo = False

### setting up sqlalchemy stuff ###
engine = create_engine(SQL_CONNECTION, echo=echo, pool_recycle=3600)
Session = scoped_session(sessionmaker(bind=engine))

class ManagedSession:
    def __enter__(self):
        self._session = Session()
        return self._session

    def __exit__(self, type, value, traceback):
        self._session.close()


def create_all():
    Base.metadata.create_all(engine)


### utilities ###
# as seen on http://stackoverflow.com/a/1383402
class ClassProperty(property):
    def __get__(self, cls, owner):
        return self.fget.__get__(None, owner)()


class Base(object):
    def __str__(self):
        return unicode(self).encode('utf-8')

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self)

    # like in django
    @classmethod
    def get_or_create(cls, defaults={}, **kwargs):
        obj = cls.get_by(**kwargs)
        if not obj:
            kwargs.update(defaults)
            obj = cls(**kwargs)
        return obj

    def _constructor(self, **kwargs):
        _declarative_constructor(self, **kwargs)
        # add self to session
        # session.add(self)

class DocumentFilterable(object):
    @classmethod
    def join_on_documents(cls, query):
        return query.join(cls)

    @classmethod
    def filter_document_query(cls, query, name):
        joined = cls.join_on_documents(query)
        with ManagedSession() as session:
            if session.query(cls).filter(cls.name == name).count() > 0:
                # print 'found exact match for %s' % (name)
                return joined.filter(cls.name == name)
            else:
                # print 'generalizing to %s' % (generalize(name))
                return joined.filter(cls.name.like(generalize(name)))


Base = declarative_base(cls=Base, constructor=Base._constructor)

### models start here ###
# this table allows the many to many relationship between Documents and Authors
author_document_table = Table('author_document', Base.metadata,
                              Column('author_id', Integer, ForeignKey('author.id')),
                              Column('document_id', Integer, ForeignKey('document.id'))
                              )


class Document(Base):
    """primary class, represents a DBLP entry. Has multiple authors and up to one journal and up to one conference. Most important field is title, from which we extract phrases, and memoize in terms."""
    __tablename__ = 'document'
    id = Column(Integer, primary_key=True)

    title = Column(UnicodeText)
    year = Column(Integer)
    terms = Column(UnicodeText)
    clean = Column(Boolean)
    authors = relationship('Author',
                           secondary=author_document_table,
                           backref='documents')
    journal_id = Column(Integer, ForeignKey('journal.id'))
    journal = relationship('Journal', backref='documents')
    conference_id = Column(Integer, ForeignKey('conference.id'))
    conference = relationship('Conference', backref='documents')

    def __unicode__(self):
        return u'(%s, %s, %s, %s)' % (self.title, self.year, self.terms, self.clean)

    def terms_list(self):
        """ read the serialized terms list and return a list of tuples, which are this doc's terms """
        t_list = []
        if self.terms is not None:
            for p in self.terms.split(','):
                s = tuple(p.split())
                if s:
                    t_list.append(s)
        return t_list

class Author(Base,DocumentFilterable):
    """Authors can have multiple papers, backreferenced through Author.documents (see Document class)"""
    __tablename__ = 'author'
    id = Column(Integer, primary_key=True)
    name = Column(UnicodeText)

    @classmethod
    def join_on_documents(cls, query):
        return query.join(Author, Document.authors)

    @classmethod
    def name_like_top(cls, name_like, n=10):
        with ManagedSession() as session:
            try:
                return session.query(Author, func.count(author_document_table.c.document_id).label('doc_count'))\
                        .filter(Author.name.like(name_like)).join(author_document_table).group_by(Author).order_by('doc_count DESC').slice(0, n).all()
            except:
                session.rollback()
                raise

    def __unicode__(self):
        return u'%s' % self.name

class Journal(Base, DocumentFilterable):
    """Journals can have multiple papers, backreferenced through Journal.documents (see Document class)"""
    __tablename__ = 'journal'
    id = Column(Integer, primary_key=True)
    name = Column(UnicodeText)

    @classmethod
    def name_like_top(cls, name_like, n=10):
        with ManagedSession() as session:
            try:
                stmt = session.query(Document.journal_id, func.count('*').label('doc_count'))\
                        .group_by(Document.journal_id)\
                        .subquery()
                return session.query(Journal, stmt.c.doc_count)\
                        .filter(Journal.name.like(name_like))\
                        .outerjoin(stmt, Journal.id == stmt.c.journal_id)\
                        .order_by('doc_count DESC').slice(0, n).all()
            except:
                session.rollback()
                raise


    def __unicode__(self):
        return u'%s' % self.name


class Conference(Base, DocumentFilterable):
    """Conferences can have multiple papers, backreferenced through Conference.documents (see Document class)"""
    __tablename__ = 'conference'
    id = Column(Integer, primary_key=True)
    name = Column(UnicodeText)

    @classmethod
    def name_like_top(cls, name_like, n=10):
        with ManagedSession() as session:
            try:
                stmt = session.query(Document.conference_id, func.count('*').label('doc_count'))\
                        .group_by(Document.conference_id)\
                        .subquery()
                return session.query(Conference, stmt.c.doc_count)\
                        .filter(Conference.name.like(name_like))\
                        .outerjoin(stmt, Conference.id == stmt.c.conference_id)\
                        .order_by('doc_count DESC').slice(0, n).all()
            except:
                session.rollback()
                raise

    def __unicode__(self):
        return u'%s' % self.name


def sliced_query(query, slice_size=10000, session_to_write=None):
    """ takes a SQLAlchemy query and allows memory-efficient iteration over a large
    rowset by buffering. If a session object is passed to session_to_write, will
    commit any changes to that session upon iterating over the number of slices in
    slice_size """
    N = query.count()
    for lower_bound in range(0, N, slice_size):
        upper_bound = min(N, lower_bound + slice_size)
        for record in query.slice(lower_bound, upper_bound):
            yield record
        if session_to_write:
            session_to_write.commit()

if __name__ == '__main__':
    engine.echo = True
    create_all()

generalize_pattern = compile(r'[\s\.]+')
def generalize(query_string):
    generalized = sub(generalize_pattern, '%', query_string)
    if not generalized.startswith('%'):
        generalized = '%' + generalized
    if not generalized.endswith('%'):
        generalized = generalized + '%'
    return generalized
