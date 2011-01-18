import MySQLdb
import unittest
import mysqlpartialdump as dumper
from cStringIO import StringIO
from mysqlpartialdump import UNIDIRECTIONAL, ALLOW_DUPLICATES

def init_connection():
    try:
        import test_config
    except ImportError:
        print '''Failed to import test_config. Please ensure test_config.py exists and is set up similar to the following:
DB_ADDRESS = '127.0.0.1'
DB_PORT = 3306
DB_USERNAME = someuser
DB_PASSWORD = somepassword
DB_NAME = somedatabase
'''
        raise 
    db = MySQLdb.connect(
            user=test_config.DB_USERNAME,
            passwd=test_config.DB_PASSWORD,
            db=test_config.DB_NAME,
            host=test_config.DB_ADDRESS,
            port=test_config.DB_PORT)
    return db

class TestImport(unittest.TestCase):

    def drop(self, cursor, name):
        try:
           cursor.execute('DROP TABLE %s'%name)
        except:
            # Ok, table already deleted
            pass

    def setUp(self):
        self.db = None
        self.db = init_connection()

        c = self.db.cursor()

        # Drop any existing tables
        self.drop(c, 'pet')
        self.drop(c, 'owner')
        self.drop(c, 'log')

        # Create a simple database
        c.execute('''
            CREATE TABLE pet (
            `id` INT NOT NULL AUTO_INCREMENT,
            `name` VARCHAR(30) NOT NULL,
            `parent_id` INT NULL,
            `owner_id` INT NOT NULL,
            PRIMARY KEY (`id`)
            );''')
        c.execute('''
            CREATE TABLE owner (
            `id` INT NOT NULL AUTO_INCREMENT,
            `name` VARCHAR(30) NOT NULL,
            PRIMARY KEY (`id`)
            );''')
        c.execute('''
            CREATE TABLE log (
            `id` INT NOT NULL AUTO_INCREMENT,
            `entity` VARCHAR(30) NOT NULL,
            `message` VARCHAR(50) NOT NULL,
            PRIMARY KEY (`id`)
            );''')


        c.close()

    def tearDown(self):
        if self.db is not None:
            self.db.close()

    def do_partial_dump(self, relationships, start_table, start_ids, pks=None):
        '''Helper method to make running a dump a bit tidier in tests'''
        if not pks:
            pks = {
                    'owner':(['id'],),
                    'pet':(['id'],),
                    'log':(['id'],),
            }
        import test_config
        result = StringIO() 
        dumper.partial_dump(
                result,
                relationships, 
                pks,
                test_config.DB_ADDRESS,
                test_config.DB_PORT,
                test_config.DB_USERNAME,
                test_config.DB_PASSWORD,
                test_config.DB_NAME,
                start_table,
                start_ids)
        return result.getvalue()

    def create_pet(self, id, name, parent_id, owner_id):
        sql = 'INSERT INTO pet(id, name, parent_id, owner_id) VALUES(%s, %s, %s, %s)'
        c = self.db.cursor()
        c.execute(sql, (id, name, parent_id, owner_id))
        self.db.commit()
        c.close()

    def create_owner(self, id, name):
        sql = 'INSERT INTO owner(id, name) VALUES(%s, %s)'
        c = self.db.cursor()
        c.execute(sql, (id, name))
        self.db.commit()
        c.close()
        
    def create_log(self, id, entity, message):
        sql = 'INSERT INTO log(id, entity, message) VALUES(%s, %s, %s)'
        c = self.db.cursor()
        c.execute(sql, (id, entity, message))
        self.db.commit()
        c.close()

    def import_dump(self, dump, clear=True):
        c = self.db.cursor()
        if clear:
            c.execute('DELETE FROM pet')
            c.execute('DELETE FROM owner')
            c.execute('DELETE FROM log')
            self.db.commit()
        c.execute(dump)
        c.close()

    def get_owners(self):
        c = self.db.cursor()
        c.execute('SELECT id, name FROM owner')
        result = {}
        while True:
            row = c.fetchone()
            if row is None:
                break
            result[row[0]] = { 'id': row[0], 'name': row[1] }
        c.close()
        return result

    def get_logs(self):
        c = self.db.cursor()
        c.execute('SELECT id, entity, message FROM log')
        result = {}
        while True:
            row = c.fetchone()
            if row is None:
                break
            result[row[0]] = { 'id': row[0], 'entity': row[1], 'message': row[2] }
        c.close()
        return result

    def get_pets(self):
        c = self.db.cursor()
        c.execute('SELECT id, name, parent_id, owner_id FROM pet')
        result = {}
        while True:
            row = c.fetchone()
            if row is None:
                break
            result[row[0]] = { 
                    'id': row[0], 
                    'name': row[1],
                    'parent_id': row[2],
                    'owner_id': row[3]
            }
        c.close()
        return result
 
    def test_single_row(self):
        self.create_owner(1, 'Bob')
        result = self.do_partial_dump({}, 'owner', 'id=1')

        # Reimporting the result should give a single row that is the same as
        # the original input
        self.import_dump(result)
        
        owners = self.get_owners()
        self.assertEquals(1, len(owners))
        self.assertEquals('Bob', owners[1]['name'])

    def test_empty_string(self):
        self.create_owner(1, '')
        result = self.do_partial_dump({}, 'owner', 'id=1')

        # An empty string should import correctly and not be saved as NULL
        print result
        self.import_dump(result)
        
        owners = self.get_owners()
        self.assertEquals(1, len(owners))
        self.assertEquals('', owners[1]['name'])

    def test_many_rows(self):
        # Importing many rows should work just the same
        # We need to test it though to ensure bulk inserts work
        for a in xrange(1, 101):
            self.create_owner(a, 'Bob')
        result = self.do_partial_dump({}, 'owner', '1=1')

        # Reimporting the result should give a single row that is the same as
        # the original input
        self.import_dump(result)
        
        owners = self.get_owners()
        self.assertEquals(100, len(owners))

    def test_forward_reference(self):
        # A reference from X to Y should cause Y be pulled in if X is pulled in
        self.create_owner(1, 'Bob')
        self.create_pet(1, 'Ginger', parent_id=None, owner_id=1)
        relations = set([
            (('owner', 'id'), ('pet', 'owner_id')),
        ])
        result = self.do_partial_dump(relations, 'owner', '1=1')

        # Reimporting the result should give a single row that is the same as
        # the original input
        self.import_dump(result)
        
        owners = self.get_owners()
        self.assertEquals(1, len(owners))

        pets = self.get_pets()
        self.assertEquals(1, len(pets))
        self.assertEquals('Ginger', pets[1]['name'])
        self.assertEquals(None, pets[1]['parent_id'])
        self.assertEquals(1, pets[1]['owner_id'])
 
    def test_multiple_value_reference(self):
        # A reference that pulls in multiple rows should work
        self.create_owner(1, 'Bob')
        self.create_pet(1, 'Ginger', parent_id=None, owner_id=1)
        self.create_pet(2, 'Tabby', parent_id=None, owner_id=1)
        relations = set([
            (('owner', 'id'), ('pet', 'owner_id')),
        ])
        result = self.do_partial_dump(relations, 'owner', '1=1')

        # Reimporting the result should give a single row that is the same as
        # the original input
        self.import_dump(result)
        
        pets = self.get_pets()
        self.assertEquals(2, len(pets))
        self.assertEquals('Ginger', pets[1]['name'])
        self.assertEquals(None, pets[1]['parent_id'])
        self.assertEquals(1, pets[1]['owner_id'])
        self.assertEquals('Tabby', pets[2]['name'])
        self.assertEquals(None, pets[2]['parent_id'])
        self.assertEquals(1, pets[2]['owner_id'])
   
    def test_back_reference(self):
        # A reference from X to Y should cause X be pulled in if Y is pulled in
        self.create_owner(1, 'Bob')
        self.create_pet(1, 'Ginger', parent_id=None, owner_id=1)
        relations = set([
            (('pet', 'owner_id'), ('owner', 'id')),
        ])
        result = self.do_partial_dump(relations, 'owner', '1=1')

        # Reimporting the result should give a single row that is the same as
        # the original input
        self.import_dump(result)
        
        owners = self.get_owners()
        self.assertEquals(1, len(owners))

        pets = self.get_pets()
        self.assertEquals(1, len(pets))
        self.assertEquals('Ginger', pets[1]['name'])
        self.assertEquals(None, pets[1]['parent_id'])
        self.assertEquals(1, pets[1]['owner_id'])
 
    def test_unidirectional_link_backwards(self):
        # Unidirectional links should only work one way. This is to account for
        # tables not having indexes when following the link backwards and hence
        # making the dump really slow
        self.create_owner(1, 'Bob')
        self.create_pet(1, 'Ginger', parent_id=None, owner_id=1)

        relations = set([
            (('pet', 'owner_id'), ('owner', 'id'), UNIDIRECTIONAL),
        ])
        result = self.do_partial_dump(relations, 'owner', '1=1')
        self.import_dump(result)
        self.assertEquals(1, len(self.get_owners()))
        self.assertEquals(0, len(self.get_pets()))

    def test_unidirectional_link_forwards(self):
        # Unidirectional links should only work one way. This is to account for
        # tables not having indexes when following the link backwards and hence
        # making the dump really slow
        self.create_owner(1, 'Bob')
        self.create_pet(1, 'Ginger', parent_id=None, owner_id=1)

        relations = set([
            (('pet', 'owner_id'), ('owner', 'id'), UNIDIRECTIONAL),
        ])
        result = self.do_partial_dump(relations, 'pet', '1=1')
        self.import_dump(result)
        self.assertEquals(1, len(self.get_owners()))
        self.assertEquals(1, len(self.get_pets()))
 
    def test_custom_relationship(self):
        # Relationships can be complicated. Callbacks can be used!
        self.create_pet(1, 'Ginger', parent_id=None, owner_id=1)
        self.create_log(1, 'Pet1', 'Hello')
        def get_logs_relationship(row):
            return ('log', ('entity', 'Pet%s'%row['id']))
        relations = set([
            ('pet', get_logs_relationship)
        ])
        result = self.do_partial_dump(relations, 'pet', '1=1')

        # Reimporting the result should give a single row that is the same as
        # the original input
        self.import_dump(result)
        
        logs = self.get_logs()
        self.assertEquals(1, len(logs))
        self.assertEquals('Pet1', logs[1]['entity'])
        self.assertEquals('Hello', logs[1]['message'])

    def test_custom_relationship_returns_none(self):
        # Relationships can be complicated. Callbacks can be used!
        self.create_pet(1, 'Ginger', parent_id=None, owner_id=1)
        self.create_log(1, 'Pet1', 'Hello')
        def get_logs_relationship(row):
            return None
        relations = set([
            ('pet', get_logs_relationship)
        ])
        result = self.do_partial_dump(relations, 'pet', '1=1')

        # Reimporting the result should give a single row that is the same as
        # the original input
        self.import_dump(result)
        
        self.assertEquals(1, len(self.get_pets()))
        self.assertEquals(0, len(self.get_logs()))

    def test_lots_of_references(self):
        # Lots of references should work fine
        for x in xrange(1, 201):
            self.create_owner(x, 'Bob')
            self.create_pet(x, 'Ginger', parent_id=None, owner_id=x)
        relations = set([
            (('pet', 'owner_id'), ('owner', 'id')),
        ])
        result = self.do_partial_dump(relations, 'owner', '1=1')
        self.import_dump(result)
       
        self.assertEquals(200, len(self.get_owners()))
        self.assertEquals(200, len(self.get_pets()))

    def test_trims_seen_ids(self):
        # If a relationship tries to follow to an ID we've already seen we 
        # should stop it
        self.create_owner(1, 'Bob')
        self.create_pet(1, 'Ginger', parent_id=None, owner_id=1)
        relations = set([
            (('pet', 'owner_id'), ('owner', 'id')),
        ])

        # Mock out the get_table method so we can track how often it is called
        original_get_table = dumper.get_table
        def mock_get_table(*args, **kwargs):
            mock_get_table.call_count += 1
            original_get_table(*args, **kwargs)
        mock_get_table.call_count = 0
        dumper.get_table = mock_get_table

        try:
            result = self.do_partial_dump(relations, 'owner', '1=1')

            # Only two tables, should only get called twice!
            self.assertEquals(2, mock_get_table.call_count)
        finally:
            dumper.get_table = original_get_table

    def test_allow_duplicates(self):
        self.create_owner(1, 'Bob')
        pks = {
                'owner':(['id'], set([ALLOW_DUPLICATES])),
                'pet':(['id'], set()),
                'log':(['id'], set()),
        }
        result = self.do_partial_dump({}, 'owner', 'id=1', pks=pks)

        # Importing the result twice should result in a single row
        self.import_dump(result)
        self.import_dump(result, clear=False)
        
        owners = self.get_owners()
        self.assertEquals(1, len(owners))
        self.assertEquals('Bob', owners[1]['name'])

    def test_simple_pks(self):
        self.create_owner(1, 'Bob')
        pks = {
                'owner':['id'],
                'pet':['id'],
                'log':['id'],
        }
        result = self.do_partial_dump({}, 'owner', 'id=1', pks=pks)
