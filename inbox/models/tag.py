from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship, backref, aliased
from sqlalchemy.sql.expression import false

from sqlalchemy.orm.collections import attribute_mapped_collection
from sqlalchemy.schema import UniqueConstraint


from inbox.sqlalchemy_ext.util import generate_public_id

from inbox.models.base import MailSyncBase
from inbox.models.constants import MAX_INDEXABLE_LENGTH
from inbox.models.mixins import HasRevisions
from inbox.models.namespace import Namespace


# FIXFIXFIX[k]: Move to mixin for Folder/ Label
class Tag(MailSyncBase, HasRevisions):
    """
    Tags represent extra data associated with threads.

    A note about the schema. The 'public_id' of a tag is immutable. For
    reserved tags such as the inbox or starred tag, the public_id is a fixed
    human-readable string. For other tags, the public_id is an autogenerated
    uid similar to a normal public id, but stored as a string for
    compatibility.

    The name of a tag is allowed to be mutable, to allow for the eventuality
    that users wish to change the name of user-created labels, or that we
    someday expose localized names ('DAS INBOX'), or that we somehow manage to
    sync renamed gmail labels, etc.

    """
    API_OBJECT_NAME = 'tag'
    namespace = relationship(
        Namespace,
        backref=backref(
            'tags',
            collection_class=attribute_mapped_collection('public_id'),
            passive_deletes=True),
        load_on_pending=True)
    namespace_id = Column(Integer, ForeignKey(
        'namespace.id', ondelete='CASCADE'), nullable=False)

    public_id = Column(String(MAX_INDEXABLE_LENGTH), nullable=False,
                       default=generate_public_id)
    name = Column(String(MAX_INDEXABLE_LENGTH), nullable=False)

    user_created = Column(Boolean, server_default=false(), nullable=False)

    CANONICAL_TAG_NAMES = ['inbox', 'archive', 'drafts', 'sending', 'sent',
                           'spam', 'starred', 'trash', 'unread', 'unseen',
                           'attachment']

    RESERVED_TAG_NAMES = ['all', 'archive', 'drafts', 'sending', 'sent',
                          'replied', 'file', 'attachment', 'unseen',
                          'important']

    # Tags that are allowed to be both added and removed via the API.
    USER_MUTABLE_TAGS = ['unread', 'starred', 'spam', 'trash', 'inbox',
                         'archive']

    @property
    def user_removable(self):
        # The 'unseen' tag can only be removed.
        return (self.user_created or self.public_id in self.USER_MUTABLE_TAGS
                or self.public_id == 'unseen')

    @property
    def user_addable(self):
        return (self.user_created or self.public_id in self.USER_MUTABLE_TAGS)

    @property
    def readonly(self):
        return not (self.user_removable or self.user_addable)

    @classmethod
    def name_available(cls, name, namespace_id, db_session):
        name = name.lower()
        if name in cls.RESERVED_TAG_NAMES or name in cls.CANONICAL_TAG_NAMES:
            return False

        if (name,) in db_session.query(Tag.name). \
                filter(Tag.namespace_id == namespace_id).all():
            return False

        return True

    unread_count = None
    thread_count = None

    def intersection(self, tag_id, db_session):
        from inbox.models.thread import TagItem

        if tag_id == self.id:
            return db_session.query(func.count(TagItem.thread_id)).\
                filter_by(tag_id=self.id).scalar()

        tagitem_alias = aliased(TagItem, name="tagitem_alias")
        query = db_session.query(func.count(1)).\
            select_from(TagItem).\
            join(tagitem_alias, TagItem.thread_id == tagitem_alias.thread_id).\
            filter(TagItem.tag_id == self.id).\
            filter(tagitem_alias.tag_id == tag_id)
        return query.scalar()

    def count_threads(self):
        return self.tagitems.count()

    __table_args__ = (UniqueConstraint('namespace_id', 'name'),
                      UniqueConstraint('namespace_id', 'public_id'))
