import json
import StringIO

from helper import web
from base import model, Fixtures, mail
from mock import patch
from itsdangerous import BadSignature
from collections import namedtuple
from pybossa.core import db, signer
from pybossa.util import unicode_csv_reader
from pybossa.util import get_user_signup_method
from bs4 import BeautifulSoup

FakeRequest = namedtuple('FakeRequest', ['text', 'status_code', 'headers'])


class TestWeb(web.Helper):
    pkg_json_not_found = {
        "help": "Return ...",
        "success": False,
        "error": {
            "message": "Not found",
            "__type": "Not Found Error"}}

    def test_01_index(self):
        """Test WEB home page works"""
        res = self.app.get("/", follow_redirects=True)
        assert self.html_title() in res.data, res
        assert "Create an App" in res.data, res

    def test_02_stats(self):
        """Test WEB leaderboard or stats page works"""
        self.register()
        self.new_application()

        app = db.session.query(model.App).first()
        # We use a string here to check that it works too
        task = model.Task(app_id=app.id, info={'n_answers': '10'})
        db.session.add(task)
        db.session.commit()

        for i in range(10):
            task_run = model.TaskRun(app_id=app.id, task_id=1,
                                     user_id=1,
                                     info={'answer': 1})
            db.session.add(task_run)
            db.session.commit()
            self.app.get('api/app/%s/newtask' % app.id)

        self.signout()

        res = self.app.get('/leaderboard', follow_redirects=True)
        assert self.html_title("Community Leaderboard") in res.data, res
        assert self.user.fullname in res.data, res.data

    def test_03_register(self):
        """Test WEB register user works"""
        res = self.app.get('/account/signin')
        assert 'Forgot Password' in res.data

        res = self.register(method="GET")
        # The output should have a mime-type: text/html
        assert res.mimetype == 'text/html', res
        assert self.html_title("Register") in res.data, res

        res = self.register()
        assert self.html_title() in res.data, res
        assert "Thanks for signing-up" in res.data, res.data

        res = self.register()
        assert self.html_title("Register") in res.data, res
        assert "The user name is already taken" in res.data, res.data

        res = self.register(fullname='')
        assert self.html_title("Register") in res.data, res
        msg = "Full name must be between 3 and 35 characters long"
        assert msg in res.data, res.data

        res = self.register(username='')
        assert self.html_title("Register") in res.data, res
        msg = "User name must be between 3 and 35 characters long"
        assert msg in res.data, res.data

        res = self.register(username='%a/$|')
        assert self.html_title("Register") in res.data, res
        msg = '$#&amp;\/| and space symbols are forbidden'
        assert msg in res.data, res.data

        res = self.register(email='')
        assert self.html_title("Register") in res.data, res.data
        assert self.html_title("Register") in res.data, res.data
        msg = "Email must be between 3 and 35 characters long"
        assert msg in res.data, res.data

        res = self.register(email='invalidemailaddress')
        assert self.html_title("Register") in res.data, res.data
        assert "Invalid email address" in res.data, res.data

        res = self.register()
        assert self.html_title("Register") in res.data, res.data
        assert "Email is already taken" in res.data, res.data

        res = self.register(password='')
        assert self.html_title("Register") in res.data, res.data
        assert "Password cannot be empty" in res.data, res.data

        res = self.register(password2='different')
        assert self.html_title("Register") in res.data, res.data
        assert "Passwords must match" in res.data, res.data

    def test_04_signin_signout(self):
        """Test WEB sign in and sign out works"""
        res = self.register()
        # Log out as the registration already logs in the user
        res = self.signout()

        res = self.signin(method="GET")
        assert self.html_title("Sign in") in res.data, res.data
        assert "Sign in" in res.data, res.data

        res = self.signin(email='')
        assert "Please correct the errors" in res.data, res
        assert "The e-mail is required" in res.data, res

        res = self.signin(password='')
        assert "Please correct the errors" in res.data, res
        assert "You must provide a password" in res.data, res

        res = self.signin(email='', password='')
        assert "Please correct the errors" in res.data, res
        assert "The e-mail is required" in res.data, res
        assert "You must provide a password" in res.data, res

        # Non-existant user
        msg = "Ooops, we didn't find you in the system"
        res = self.signin(email='wrongemail')
        assert msg in res.data, res.data

        res = self.signin(email='wrongemail', password='wrongpassword')
        assert msg in res.data, res

        # Real user but wrong password or username
        msg = "Ooops, Incorrect email/password"
        res = self.signin(password='wrongpassword')
        assert msg in res.data, res

        res = self.signin()
        assert self.html_title() in res.data, res
        assert "Welcome back %s" % self.user.fullname in res.data, res

        # Check profile page with several information chunks
        res = self.profile()
        assert self.html_title("Profile") in res.data, res
        assert self.user.fullname in res.data, res
        assert self.user.email_addr in res.data, res

        # Log out
        res = self.signout()
        assert self.html_title() in res.data, res
        assert "You are now signed out" in res.data, res

        # Request profile as an anonymous user
        res = self.profile()
        # As a user must be signed in to access, the page the title will be the
        # redirection to log in
        assert self.html_title("Sign in") in res.data, res
        assert "Please sign in to access this page." in res.data, res

        res = self.signin(next='%2Faccount%2Fprofile')
        assert self.html_title("Profile") in res.data, res
        assert "Welcome back %s" % self.user.fullname in res.data, res

    def test_05_update_user_profile(self):
        """Test WEB update user profile"""

        # Create an account and log in
        self.register()

        # Update profile with new data
        res = self.update_profile(method="GET")
        msg = "Update your profile: %s" % self.user.fullname
        assert self.html_title(msg) in res.data, res
        msg = 'input id="id" name="id" type="hidden" value="1"'
        assert msg in res.data, res
        assert self.user.fullname in res.data, res
        assert "Save the changes" in res.data, res
        msg = '<a href="/account/profile/settings" class="btn">Cancel</a>'
        assert  msg in res.data, res

        res = self.update_profile(fullname="John Doe 2",
                                  email_addr="johndoe2@example.com",
                                  locale="en")
        assert self.html_title("Profile") in res.data, res.data
        assert "Your profile has been updated!" in res.data, res.data
        assert "John Doe 2" in res.data, res
        assert "johndoe" in res.data, res
        assert "johndoe2@example.com" in res.data, res

        # Updating the username field forces the user to re-log in
        res = self.update_profile(fullname="John Doe 2",
                                  email_addr="johndoe2@example.com",
                                  locale="en",
                                  name="johndoe2")
        assert "Your profile has been updated!" in res.data, res
        assert "Please sign in to access this page" in res.data, res

        res = self.signin(method="POST", email="johndoe2@example.com",
                          password="p4ssw0rd",
                          next="%2Faccount%2Fprofile")
        assert "Welcome back John Doe 2" in res.data, res.data
        assert "John Doe 2" in res.data, res
        assert "johndoe2" in res.data, res
        assert "johndoe2@example.com" in res.data, res

        res = self.signout()
        assert self.html_title() in res.data, res
        assert "You are now signed out" in res.data, res

        # A user must be signed in to access the update page, the page
        # the title will be the redirection to log in
        res = self.update_profile(method="GET")
        assert self.html_title("Sign in") in res.data, res
        assert "Please sign in to access this page." in res.data, res

        # A user must be signed in to access the update page, the page
        # the title will be the redirection to log in
        res = self.update_profile()
        assert self.html_title("Sign in") in res.data, res
        assert "Please sign in to access this page." in res.data, res

    def test_05a_get_nonexistant_app(self):
        """Test WEB get not existant app should return 404"""
        res = self.app.get('/app/nonapp', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

    def test_05b_get_nonexistant_app_newtask(self):
        """Test WEB get non existant app newtask should return 404"""
        res = self.app.get('/app/noapp/presenter', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        res = self.app.get('/app/noapp/newtask', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

    def test_05c_get_nonexistant_app_tutorial(self):
        """Test WEB get non existant app tutorial should return 404"""
        res = self.app.get('/app/noapp/tutorial', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

    def test_05d_get_nonexistant_app_delete(self):
        """Test WEB get non existant app delete should return 404"""
        self.register()
        # GET
        res = self.app.get('/app/noapp/delete', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.data
        # POST
        res = self.delete_application(short_name="noapp")
        assert res.status == '404 NOT FOUND', res.status

    def test_05d_get_nonexistant_app_update(self):
        """Test WEB get non existant app update should return 404"""
        self.register()
        # GET
        res = self.app.get('/app/noapp/update', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        # POST
        res = self.update_application(short_name="noapp")
        assert res.status == '404 NOT FOUND', res.status

    def test_05d_get_nonexistant_app_import(self):
        """Test WEB get non existant app import should return 404"""
        self.register()
        # GET
        res = self.app.get('/app/noapp/import', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        # POST
        res = self.app.post('/app/noapp/import', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

    def test_05d_get_nonexistant_app_task(self):
        """Test WEB get non existant app task should return 404"""
        res = self.app.get('/app/noapp/task', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        # Pagination
        res = self.app.get('/app/noapp/task/25', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

    def test_05d_get_nonexistant_app_results_json(self):
        """Test WEB get non existant app results json should return 404"""
        res = self.app.get('/app/noapp/24/results.json', follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

    def test_06_applications_without_apps(self):
        """Test WEB applications index without apps works"""
        # Check first without apps
        Fixtures.create_categories()
        res = self.app.get('/app', follow_redirects=True)
        assert "Applications" in res.data, res.data
        assert Fixtures.cat_1 in res.data, res.data

    def test_06_applications_2(self):
        """Test WEB applications index with apps"""
        Fixtures.create()

        res = self.app.get('/app', follow_redirects=True)
        assert self.html_title("Applications") in res.data, res.data
        assert "Applications" in res.data, res.data
        assert Fixtures.app_short_name in res.data, res.data

    def test_06_featured_apps(self):
        """Test WEB application index shows featured apps in all the pages works"""
        Fixtures.create()

        f = model.Featured()
        f.app_id = 1
        db.session.add(f)
        db.session.commit()

        res = self.app.get('/app', follow_redirects=True)
        assert self.html_title("Applications") in res.data, res.data
        assert "Applications" in res.data, res.data
        assert '/app/test-app' in res.data, res.data
        assert '<h2><a href="/app/test-app/">My New App</a></h2>' in res.data, res.data

    @patch('pybossa.ckan.requests.get')
    def test_10_get_application(self, Mock):
        """Test WEB application URL/<short_name> works"""
        # Sign in and create an application
        html_request = FakeRequest(json.dumps(self.pkg_json_not_found), 200,
                                   {'content-type': 'application/json'})
        Mock.return_value = html_request
        self.register()
        res = self.new_application()

        res = self.app.get('/app/sampleapp', follow_redirects=True)
        msg = "Application: Sample App"
        assert self.html_title(msg) in res.data, res
        err_msg = "There should be a contribute button"
        assert "Start Contributing Now" in res.data, err_msg

        res = self.app.get('/app/sampleapp/settings', follow_redirects=True)
        assert res.status == '200 OK', res.status
        self.signout()

        # Now as an anonymous user
        res = self.app.get('/app/sampleapp', follow_redirects=True)
        assert self.html_title("Application: Sample App") in res.data, res
        assert "Start Contributing Now" in res.data, err_msg
        res = self.app.get('/app/sampleapp/settings', follow_redirects=True)
        assert res.status == '200 OK', res.status
        err_msg = "Anonymous user should be redirected to sign in page"
        assert "Please sign in to access this page" in res.data, err_msg

        # Now with a different user
        self.register(fullname="Perico Palotes", username="perico")
        res = self.app.get('/app/sampleapp', follow_redirects=True)
        assert self.html_title("Application: Sample App") in res.data, res
        assert "Start Contributing Now" in res.data, err_msg
        res = self.app.get('/app/sampleapp/settings')
        assert res.status == '401 UNAUTHORIZED', res.status

    def test_11_create_application(self):
        """Test WEB create an application works"""
        # Create an app as an anonymous user
        res = self.new_application(method="GET")
        assert self.html_title("Sign in") in res.data, res
        assert "Please sign in to access this page" in res.data, res

        res = self.new_application()
        assert self.html_title("Sign in") in res.data, res.data
        assert "Please sign in to access this page." in res.data, res.data

        # Sign in and create an application
        res = self.register()

        res = self.new_application(method="GET")
        assert self.html_title("Create an Application") in res.data, res
        assert "Create the application" in res.data, res

        res = self.new_application()
        assert "<strong>Sample App</strong>: Settings" in res.data, res
        assert "Application created!" in res.data, res

        app = db.session.query(model.App).first()
        assert app.name == 'Sample App', 'Different names %s' % app.name
        assert app.short_name == 'sampleapp', \
            'Different names %s' % app.short_name
        assert app.info['thumbnail'] == 'An Icon link', \
            "Thumbnail should be the same: %s" % app.info['thumbnail']
        assert app.long_description == '<div id="long_desc">Long desc</div>', \
            "Long desc should be the same: %s" % app.long_description

    def test_11_a_create_application_errors(self):
        """Test WEB create an application issues the errors"""
        self.register()
        # Required fields checks
        # Issue the error for the app.name
        res = self.new_application(name=None)
        err_msg = "An application must have a name"
        assert "This field is required" in res.data, err_msg

        # Issue the error for the app.short_name
        res = self.new_application(short_name=None)
        err_msg = "An application must have a short_name"
        assert "This field is required" in res.data, err_msg

        # Issue the error for the app.description
        res = self.new_application(description=None)
        err_msg = "An application must have a description"
        assert "You must provide a description" in res.data, err_msg

        # Issue the error for the app.short_name
        res = self.new_application(short_name='$#/|')
        err_msg = "An application must have a short_name without |/$# chars"
        assert '$#&amp;\/| and space symbols are forbidden' in res.data, err_msg

        # Now Unique checks
        self.new_application()
        res = self.new_application()
        err_msg = "There should be a Unique field"
        assert "Name is already taken" in res.data, err_msg
        assert "Short Name is already taken" in res.data, err_msg

    @patch('pybossa.ckan.requests.get')
    def test_12_update_application(self, Mock):
        """Test WEB update application works"""
        html_request = FakeRequest(json.dumps(self.pkg_json_not_found), 200,
                                   {'content-type': 'application/json'})
        Mock.return_value = html_request

        self.register()
        self.new_application()

        # Get the Update App web page
        res = self.update_application(method="GET")
        msg = "Application: Sample App &middot; Update"
        assert self.html_title(msg) in res.data, res
        msg = 'input id="id" name="id" type="hidden" value="1"'
        assert msg in res.data, res
        assert "Save the changes" in res.data, res

        # Update the application
        res = self.update_application(new_name="New Sample App",
                                      new_short_name="newshortname",
                                      new_description="New description",
                                      new_thumbnail="New Icon Link",
                                      new_long_description='New long desc',
                                      new_hidden=True)
        app = db.session.query(model.App).first()
        assert "Application updated!" in res.data, res
        err_msg = "App name not updated %s" % app.name
        assert app.name == "New Sample App", err_msg
        err_msg = "App short name not updated %s" % app.short_name
        assert app.short_name == "newshortname", err_msg
        err_msg = "App description not updated %s" % app.description
        assert app.description == "New description", err_msg
        err_msg = "App thumbnail not updated %s" % app.info['thumbnail']
        assert app.info['thumbnail'] == "New Icon Link", err_msg
        err_msg = "App long description not updated %s" % app.long_description
        assert app.long_description == "New long desc", err_msg
        err_msg = "App hidden not updated %s" % app.hidden
        assert app.hidden == 1, err_msg

    @patch('pybossa.ckan.requests.get')
    def test_13_hidden_applications(self, Mock):
        """Test WEB hidden application works"""
        html_request = FakeRequest(json.dumps(self.pkg_json_not_found), 200,
                                   {'content-type': 'application/json'})
        Mock.return_value = html_request
        self.register()
        self.new_application()
        self.update_application(new_hidden=True)
        self.signout()

        res = self.app.get('/app/', follow_redirects=True)
        assert "Sample App" not in res.data, res

        res = self.app.get('/app/sampleapp', follow_redirects=True)
        err_msg = "Hidden apps should return a 403"
        res.status_code == 403, err_msg

    @patch('pybossa.ckan.requests.get')
    def test_13a_hidden_applications_owner(self, Mock):
        """Test WEB hidden applications are shown to their owners"""
        html_request = FakeRequest(json.dumps(self.pkg_json_not_found), 200,
                                   {'content-type': 'application/json'})
        Mock.return_value = html_request

        self.register()
        self.new_application()
        self.update_application(new_hidden=True)

        res = self.app.get('/app/', follow_redirects=True)
        assert "Sample App" not in res.data, ("Applications should be hidden"
                                              "in the index")

        res = self.app.get('/app/sampleapp', follow_redirects=True)
        assert "Sample App" in res.data, ("Application should be shown to"
                                          "the owner")

    def test_14_delete_application(self):
        """Test WEB delete application works"""
        self.register()
        self.new_application()
        res = self.delete_application(method="GET")
        msg = "Application: Sample App &middot; Delete"
        assert self.html_title(msg) in res.data, res
        assert "No, do not delete it" in res.data, res

        res = self.delete_application()
        assert "Application deleted!" in res.data, res

    def test_15_twitter_email_warning(self):
        """Test WEB Twitter email warning works"""
        # This test assumes that the user allows Twitter to authenticate,
        #  returning a valid resp. The only difference is a user object
        #  without a password
        #  Register a user and sign out
        user = model.User(name="tester", passwd_hash="tester",
                          fullname="tester",
                          email_addr="tester")
        user.set_password('tester')
        db.session.add(user)
        db.session.commit()
        db.session.query(model.User).all()

        # Sign in again and check the warning message
        self.signin(email="tester", password="tester")
        res = self.app.get('/', follow_redirects=True)
        msg = "Please update your e-mail address in your profile page, " \
              "right now it is empty!"
        user = db.session.query(model.User).get(1)
        assert msg in res.data, res.data

    def test_16_task_status_completed(self):
        """Test WEB Task Status Completed works"""
        self.register()
        self.new_application()

        app = db.session.query(model.App).first()
        # We use a string here to check that it works too
        task = model.Task(app_id=app.id, info={'n_answers': '10'})
        db.session.add(task)
        db.session.commit()

        res = self.app.get('app/%s/tasks/browse' % (app.short_name),
                           follow_redirects=True)
        dom = BeautifulSoup(res.data)
        assert "Sample App" in res.data, res.data
        assert '0 of 10' in res.data, res.data
        err_msg = "Download button should be disabled"
        assert dom.find(id='nothingtodownload') is not None, err_msg

        for i in range(5):
            task_run = model.TaskRun(app_id=app.id, task_id=1,
                                     info={'answer': 1})
            db.session.add(task_run)
            db.session.commit()
            self.app.get('api/app/%s/newtask' % app.id)

        res = self.app.get('app/%s/tasks/browse' % (app.short_name),
                           follow_redirects=True)
        dom = BeautifulSoup(res.data)
        assert "Sample App" in res.data, res.data
        assert '5 of 10' in res.data, res.data
        err_msg = "Download Partial results button should be shown"
        assert dom.find(id='partialdownload') is not None, err_msg

        for i in range(5):
            task_run = model.TaskRun(app_id=app.id, task_id=1,
                                     info={'answer': 1})
            db.session.add(task_run)
            db.session.commit()
            self.app.get('api/app/%s/newtask' % app.id)

        self.signout()

        app = db.session.query(model.App).first()

        res = self.app.get('app/%s/tasks/browse' % (app.short_name),
                           follow_redirects=True)
        assert "Sample App" in res.data, res.data
        msg = 'Task <span class="label label-success">#1</span>'
        assert msg in res.data, res.data
        assert '10 of 10' in res.data, res.data
        dom = BeautifulSoup(res.data)
        err_msg = "Download Full results button should be shown"
        assert dom.find(id='fulldownload') is not None, err_msg

    def test_17_export_task_runs(self):
        """Test WEB TaskRun export works"""
        self.register()
        self.new_application()

        app = db.session.query(model.App).first()
        task = model.Task(app_id=app.id, info={'n_answers': 10})
        db.session.add(task)
        db.session.commit()

        for i in range(10):
            task_run = model.TaskRun(app_id=app.id, task_id=1,
                                     info={'answer': 1})
            db.session.add(task_run)
            db.session.commit()

        self.signout()

        app = db.session.query(model.App).first()
        res = self.app.get('app/%s/%s/results.json' % (app.short_name, 1),
                           follow_redirects=True)
        data = json.loads(res.data)
        assert len(data) == 10, data
        for tr in data:
            assert tr['info']['answer'] == 1, tr

    def test_18_task_status_wip(self):
        """Test WEB Task Status on going works"""
        self.register()
        self.new_application()

        app = db.session.query(model.App).first()
        task = model.Task(app_id=app.id, info={'n_answers': 10})
        db.session.add(task)
        db.session.commit()
        self.signout()

        app = db.session.query(model.App).first()

        res = self.app.get('app/%s/tasks/browse' % (app.short_name),
                           follow_redirects=True)
        assert "Sample App" in res.data, res.data
        msg = 'Task <span class="label label-info">#1</span>'
        assert msg in res.data, res.data
        assert '0 of 10' in res.data, res.data

    def test_19_app_index_categories(self):
        """Test WEB Application Index categories works"""
        self.register()
        self.new_application()
        self.signout()

        res = self.app.get('app', follow_redirects=True)
        assert "Applications" in res.data, res.data
        assert Fixtures.cat_1 in res.data, res.data

    def test_20_app_index_published(self):
        """Test WEB Application Index published works"""
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        info = dict(task_presenter="some html")
        app.info = info
        db.session.commit()
        task = model.Task(app_id=app.id, info={'n_answers': 10})
        db.session.add(task)
        db.session.commit()
        self.signout()

        res = self.app.get('app', follow_redirects=True)
        assert "Applications" in res.data, res.data
        assert Fixtures.cat_1 in res.data, res.data
        assert "draft" not in res.data, res.data
        assert "Sample App" in res.data, res.data

    def test_20_app_index_draft(self):
        """Test WEB Application Index draft works"""
        # Create root
        self.register()
        self.new_application()
        self.signout()
        # Create a user
        self.register(fullname="jane", username="jane", email="jane@jane.com")
        self.signout()

        # As Anonymous
        res = self.app.get('/app/draft', follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "Anonymous should not see draft apps"
        assert dom.find(id='signin') is not None, err_msg

        # As authenticated but not admin
        self.signin(email="jane@jane.com", password="p4ssw0rd")
        res = self.app.get('/app/draft', follow_redirects=True)
        assert res.status_code == 403, "Non-admin should not see draft apps"
        self.signout()

        # As Admin
        self.signin()
        res = self.app.get('/app/draft', follow_redirects=True)
        assert "Applications" in res.data, res.data
        assert "app-published" not in res.data, res.data
        assert "draft" in res.data, res.data
        assert "Sample App" in res.data, res.data

    def test_21_get_specific_ongoing_task_anonymous(self):
        """Test WEB get specific ongoing task_id for
        an app works as anonymous"""

        Fixtures.create()
        self.delTaskRuns()
        app = db.session.query(model.App).first()
        task = db.session.query(model.Task)\
                 .filter(model.App.id == app.id)\
                 .first()
        res = self.app.get('app/%s/task/%s' % (app.short_name, task.id),
                           follow_redirects=True)
        assert 'TaskPresenter' in res.data, res.data
        msg = "?next=%2Fapp%2F" + app.short_name + "%2Ftask%2F" + str(task.id)
        assert msg in res.data, res.data

    def test_22_get_specific_completed_task_anonymous(self):
        """Test WEB get specific completed task_id
        for an app works as anonymous"""

        model.rebuild_db()
        Fixtures.create()
        app = db.session.query(model.App).first()
        task = db.session.query(model.Task)\
                 .filter(model.App.id == app.id)\
                 .first()

        for i in range(10):
            task_run = model.TaskRun(app_id=app.id, task_id=task.id,
                                     user_ip="127.0.0.1", info={'answer': 1})
            db.session.add(task_run)
            db.session.commit()

        ntask = model.Task(id=task.id, state='completed')

        assert ntask not in db.session
        db.session.merge(ntask)
        db.session.commit()

        res = self.app.get('app/%s/task/%s' % (app.short_name, task.id),
                           follow_redirects=True)
        msg = 'You have already participated in this task'
        assert msg in res.data, res.data
        assert 'Try with another one' in res.data, res.data

    def test_23_get_specific_ongoing_task_user(self):
        """Test WEB get specific ongoing task_id for an app works as an user"""

        Fixtures.create()
        self.delTaskRuns()
        self.register()
        self.signin()
        app = db.session.query(model.App).first()
        task = db.session.query(model.Task)\
                 .filter(model.App.id == app.id)\
                 .first()
        res = self.app.get('app/%s/task/%s' % (app.short_name, task.id),
                           follow_redirects=True)
        assert 'TaskPresenter' in res.data, res.data
        self.signout()

    def test_24_get_specific_completed_task_user(self):
        """Test WEB get specific completed task_id
        for an app works as an user"""

        model.rebuild_db()
        Fixtures.create()
        self.register()

        user = db.session.query(model.User)\
                 .filter(model.User.name == self.user.username)\
                 .first()
        app = db.session.query(model.App).first()
        task = db.session.query(model.Task)\
                 .filter(model.App.id == app.id)\
                 .first()
        for i in range(10):
            task_run = model.TaskRun(app_id=app.id, task_id=task.id, user_id=user.id,
                                     info={'answer': 1})
            db.session.add(task_run)
            db.session.commit()
            #self.app.get('api/app/%s/newtask' % app.id)

        ntask = model.Task(id=task.id, state='completed')
        #self.signin()
        assert ntask not in db.session
        db.session.merge(ntask)
        db.session.commit()

        res = self.app.get('app/%s/task/%s' % (app.short_name, task.id),
                           follow_redirects=True)
        msg = 'You have already participated in this task'
        assert msg in res.data, res.data
        assert 'Try with another one' in res.data, res.data
        self.signout()

    def test_25_get_wrong_task_app(self):
        """Test WEB get wrong task.id for an app works"""

        model.rebuild_db()
        Fixtures.create()
        app1 = db.session.query(model.App).get(1)
        app1_short_name = app1.short_name

        db.session.query(model.Task)\
                  .filter(model.Task.app_id == 1)\
                  .first()

        self.register()
        self.new_application()
        app2 = db.session.query(model.App).get(2)
        self.new_task(app2.id)
        task2 = db.session.query(model.Task)\
                  .filter(model.Task.app_id == 2)\
                  .first()
        task2_id = task2.id
        self.signout()

        res = self.app.get('/app/%s/task/%s' % (app1_short_name, task2_id))
        assert "Error" in res.data, res.data
        msg = "This task does not belong to %s" % app1_short_name
        assert msg in res.data, res.data

    def test_26_tutorial_signed_user(self):
        """Test WEB tutorials work as signed in user"""
        Fixtures.create()
        app1 = db.session.query(model.App).get(1)
        app1.info = dict(tutorial="some help")
        db.session.commit()
        self.register()
        # First time accessing the app should redirect me to the tutorial
        res = self.app.get('/app/test-app/newtask', follow_redirects=True)
        err_msg = "There should be some tutorial for the application"
        assert "some help" in res.data, err_msg
        # Second time should give me a task, and not the tutorial
        res = self.app.get('/app/test-app/newtask', follow_redirects=True)
        assert "some help" not in res.data

    def test_27_tutorial_anonymous_user(self):
        """Test WEB tutorials work as an anonymous user"""
        Fixtures.create()
        app1 = db.session.query(model.App).get(1)
        app1.info = dict(tutorial="some help")
        db.session.commit()
        #self.register()
        # First time accessing the app should redirect me to the tutorial
        res = self.app.get('/app/test-app/newtask', follow_redirects=True)
        err_msg = "There should be some tutorial for the application"
        assert "some help" in res.data, err_msg
        # Second time should give me a task, and not the tutorial
        res = self.app.get('/app/test-app/newtask', follow_redirects=True)
        assert "some help" not in res.data

    def test_28_non_tutorial_signed_user(self):
        """Test WEB app without tutorial work as signed in user"""
        Fixtures.create()
        db.session.commit()
        self.register()
        # First time accessing the app should redirect me to the tutorial
        res = self.app.get('/app/test-app/newtask', follow_redirects=True)
        err_msg = "There should not be a tutorial for the application"
        assert "some help" not in res.data, err_msg
        # Second time should give me a task, and not the tutorial
        res = self.app.get('/app/test-app/newtask', follow_redirects=True)
        assert "some help" not in res.data

    def test_29_tutorial_anonymous_user(self):
        """Test WEB app without tutorials work as an anonymous user"""
        Fixtures.create()
        db.session.commit()
        self.register()
        # First time accessing the app should redirect me to the tutorial
        res = self.app.get('/app/test-app/newtask', follow_redirects=True)
        err_msg = "There should not be a tutorial for the application"
        assert "some help" not in res.data, err_msg
        # Second time should give me a task, and not the tutorial
        res = self.app.get('/app/test-app/newtask', follow_redirects=True)
        assert "some help" not in res.data

    def test_30_app_id_owner(self):
        """Test WEB application settings page shows the ID to the owner"""
        self.register()
        self.new_application()

        res = self.app.get('/app/sampleapp/settings', follow_redirects=True)
        assert "Sample App" in res.data, ("Application should be shown to "
                                          "the owner")
        msg = '<strong><i class="icon-cog"></i> ID</strong>: 1'
        err_msg = "Application ID should be shown to the owner"
        assert msg in res.data, err_msg

    @patch('pybossa.ckan.requests.get')
    def test_30_app_id_anonymous_user(self, Mock):
        """Test WEB application page does not show the ID to anonymous users"""
        html_request = FakeRequest(json.dumps(self.pkg_json_not_found), 200,
                                   {'content-type': 'application/json'})
        Mock.return_value = html_request

        self.register()
        self.new_application()
        self.signout()

        res = self.app.get('/app/sampleapp', follow_redirects=True)
        assert "Sample App" in res.data, ("Application name should be shown"
                                          " to users")
        assert '<strong><i class="icon-cog"></i> ID</strong>: 1' not in \
            res.data, "Application ID should be shown to the owner"

    def test_31_user_profile_progress(self):
        """Test WEB user progress profile page works"""
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        task = model.Task(app_id=app.id, info={'n_answers': '10'})
        db.session.add(task)
        db.session.commit()
        for i in range(10):
            task_run = model.TaskRun(app_id=app.id, task_id=1, user_id=1,
                                     info={'answer': 1})
            db.session.add(task_run)
            db.session.commit()
            self.app.get('api/app/%s/newtask' % app.id)

        res = self.app.get('account/profile', follow_redirects=True)
        assert "Sample App" in res.data, res.data
        assert "You have contributed <strong>10</strong> tasks" in res.data, res.data
        assert "Contribute!" in res.data, "There should be a Contribute button"

    def test_32_oauth_password(self):
        """Test WEB user sign in without password works"""
        user = model.User(email_addr="johndoe@johndoe.com",
                          name=self.user.username,
                          passwd_hash=None,
                          fullname=self.user.fullname,
                          api_key="api-key")
        db.session.add(user)
        db.session.commit()
        res = self.signin()
        assert "Ooops, we didn't find you in the system" in res.data, res.data

    @patch('pybossa.view.importer.requests.get')
    def test_33_bulk_csv_import_unauthorized(self, Mock):
        """Test WEB bulk import unauthorized works"""
        unauthorized_request = FakeRequest('Unauthorized', 403,
                                           {'content-type': 'text/csv'})
        Mock.return_value = unauthorized_request
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        url = '/app/%s/tasks/import?template=csv' % (app.short_name)
        res = self.app.post(url, data={'csv_url': 'http://myfakecsvurl.com',
                                       'formtype': 'csv'},
                            follow_redirects=True)
        msg = "Oops! It looks like you don't have permission to access that file"
        assert msg in res.data

    @patch('pybossa.view.importer.requests.get')
    def test_34_bulk_csv_import_non_html(self, Mock):
        """Test WEB bulk import non html works"""
        html_request = FakeRequest('Not a CSV', 200,
                                   {'content-type': 'text/html'})
        Mock.return_value = html_request
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        url = '/app/%s/tasks/import?template=csv' % (app.short_name)
        res = self.app.post(url, data={'csv_url': 'http://myfakecsvurl.com'},
                            follow_redirects=True)
        assert "Oops! That file doesn't look like the right file." in res.data

    @patch('pybossa.view.importer.requests.get')
    def test_35_bulk_csv_import_non_html(self, Mock):
        """Test WEB bulk import non html works"""
        empty_file = FakeRequest('CSV,with,no,content\n', 200,
                                 {'content-type': 'text/plain'})
        Mock.return_value = empty_file
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        url = '/app/%s/tasks/import?template=csv' % (app.short_name)
        res = self.app.post(url, data={'csv_url': 'http://myfakecsvurl.com',
                                       'formtype': 'csv'},
                            follow_redirects=True)
        assert "Oops! It looks like the file is empty." in res.data

    @patch('pybossa.view.importer.requests.get')
    def test_36_bulk_csv_import_dup_header(self, Mock):
        """Test WEB bulk import duplicate header works"""
        empty_file = FakeRequest('Foo,Bar,Foo\n1,2,3', 200,
                                 {'content-type': 'text/plain'})
        Mock.return_value = empty_file
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        url = '/app/%s/tasks/import?template=csv' % (app.short_name)
        res = self.app.post(url, data={'csv_url': 'http://myfakecsvurl.com',
                                       'formtype': 'csv'},
                            follow_redirects=True)
        msg = "The file you uploaded has two headers with the same name"
        assert msg in res.data

    @patch('pybossa.view.importer.requests.get')
    def test_37_bulk_csv_import_no_column_names(self, Mock):
        """Test WEB bulk import no column names works"""
        empty_file = FakeRequest('Foo,Bar,Baz\n1,2,3', 200,
                                 {'content-type': 'text/plain'})
        Mock.return_value = empty_file
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        url = '/app/%s/tasks/import?template=csv' % (app.short_name)
        res = self.app.post(url, data={'csv_url': 'http://myfakecsvurl.com',
                                       'formtype': 'csv'},
                            follow_redirects=True)
        task = db.session.query(model.Task).first()
        assert {u'Bar': u'2', u'Foo': u'1', u'Baz': u'3'} == task.info
        assert "1 Task imported successfully!" in res.data

    @patch('pybossa.view.importer.requests.get')
    def test_38_bulk_csv_import_with_column_name(self, Mock):
        """Test WEB bulk import with column name works"""
        empty_file = FakeRequest('Foo,Bar,priority_0\n1,2,3', 200,
                                 {'content-type': 'text/plain'})
        Mock.return_value = empty_file
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        url = '/app/%s/tasks/import?template=csv' % (app.short_name)
        res = self.app.post(url, data={'csv_url': 'http://myfakecsvurl.com',
                                       'formtype': 'csv'},
                            follow_redirects=True)
        task = db.session.query(model.Task).first()
        assert {u'Bar': u'2', u'Foo': u'1'} == task.info
        assert task.priority_0 == 3
        assert "1 Task imported successfully!" in res.data

        # Check that only new items are imported
        empty_file = FakeRequest('Foo,Bar,priority_0\n1,2,3\n4,5,6', 200,
                                 {'content-type': 'text/plain'})
        Mock.return_value = empty_file
        app = db.session.query(model.App).first()
        url = '/app/%s/tasks/import?template=csv' % (app.short_name)
        res = self.app.post(url, data={'csv_url': 'http://myfakecsvurl.com',
                                       'formtype': 'csv'},
                            follow_redirects=True)
        app = db.session.query(model.App).first()
        assert len(app.tasks) == 2, "There should be only 2 tasks"
        n = 0
        csv_tasks = [{u'Foo': u'1', u'Bar': u'2'}, {u'Foo': u'4', u'Bar': u'5'}]
        for t in app.tasks:
            assert t.info == csv_tasks[n], "The task info should be the same"
            n += 1

    def test_39_google_oauth_creation(self):
        """Test WEB Google OAuth creation of user works"""
        fake_response = {
            u'access_token': u'access_token',
            u'token_type': u'Bearer',
            u'expires_in': 3600,
            u'id_token': u'token'}

        fake_user = {
            u'family_name': u'Doe', u'name': u'John Doe',
            u'picture': u'https://goo.gl/img.jpg',
            u'locale': u'en',
            u'gender': u'male',
            u'email': u'john@gmail.com',
            u'birthday': u'0000-01-15',
            u'link': u'https://plus.google.com/id',
            u'given_name': u'John',
            u'id': u'111111111111111111111',
            u'verified_email': True}

        from pybossa.view import google
        response_user = google.manage_user(fake_response['access_token'],
                                           fake_user, None)

        user = db.session.query(model.User).get(1)

        assert user.email_addr == response_user.email_addr, response_user

    def test_40_google_oauth_creation(self):
        """Test WEB Google OAuth detects same user name/email works"""
        fake_response = {
            u'access_token': u'access_token',
            u'token_type': u'Bearer',
            u'expires_in': 3600,
            u'id_token': u'token'}

        fake_user = {
            u'family_name': u'Doe', u'name': u'John Doe',
            u'picture': u'https://goo.gl/img.jpg',
            u'locale': u'en',
            u'gender': u'male',
            u'email': u'john@gmail.com',
            u'birthday': u'0000-01-15',
            u'link': u'https://plus.google.com/id',
            u'given_name': u'John',
            u'id': u'111111111111111111111',
            u'verified_email': True}

        self.register()
        self.signout()

        from pybossa.view import google
        response_user = google.manage_user(fake_response['access_token'],
                                           fake_user, None)

        assert response_user is None, response_user

    def test_39_facebook_oauth_creation(self):
        """Test WEB Facebook OAuth creation of user works"""
        fake_response = {
            u'access_token': u'access_token',
            u'token_type': u'Bearer',
            u'expires_in': 3600,
            u'id_token': u'token'}

        fake_user = {
            u'username': u'teleyinex',
            u'first_name': u'John',
            u'last_name': u'Doe',
            u'verified': True,
            u'name': u'John Doe',
            u'locale': u'en_US',
            u'gender': u'male',
            u'email': u'johndoe@example.com',
            u'quotes': u'"quote',
            u'link': u'http://www.facebook.com/johndoe',
            u'timezone': 1,
            u'updated_time': u'2011-11-11T12:33:52+0000',
            u'id': u'11111'}

        from pybossa.view import facebook
        response_user = facebook.manage_user(fake_response['access_token'],
                                             fake_user, None)

        user = db.session.query(model.User).get(1)

        assert user.email_addr == response_user.email_addr, response_user

    def test_40_facebook_oauth_creation(self):
        """Test WEB Facebook OAuth detects same user name/email works"""
        fake_response = {
            u'access_token': u'access_token',
            u'token_type': u'Bearer',
            u'expires_in': 3600,
            u'id_token': u'token'}

        fake_user = {
            u'username': u'teleyinex',
            u'first_name': u'John',
            u'last_name': u'Doe',
            u'verified': True,
            u'name': u'John Doe',
            u'locale': u'en_US',
            u'gender': u'male',
            u'email': u'johndoe@example.com',
            u'quotes': u'"quote',
            u'link': u'http://www.facebook.com/johndoe',
            u'timezone': 1,
            u'updated_time': u'2011-11-11T12:33:52+0000',
            u'id': u'11111'}

        self.register()
        self.signout()

        from pybossa.view import facebook
        response_user = facebook.manage_user(fake_response['access_token'],
                                             fake_user, None)

        assert response_user is None, response_user

    def test_39_twitter_oauth_creation(self):
        """Test WEB Twitter OAuth creation of user works"""
        fake_response = {
            u'access_token': {u'oauth_token': u'oauth_token',
                              u'oauth_token_secret': u'oauth_token_secret'},
            u'token_type': u'Bearer',
            u'expires_in': 3600,
            u'id_token': u'token'}

        fake_user = {u'screen_name': u'johndoe',
                     u'user_id': u'11111'}

        from pybossa.view import twitter
        response_user = twitter.manage_user(fake_response['access_token'],
                                            fake_user, None)

        user = db.session.query(model.User).get(1)

        assert user.email_addr == response_user.email_addr, response_user

    def test_40_twitter_oauth_creation(self):
        """Test WEB Twitter OAuth detects same user name/email works"""
        fake_response = {
            u'access_token': {u'oauth_token': u'oauth_token',
                              u'oauth_token_secret': u'oauth_token_secret'},
            u'token_type': u'Bearer',
            u'expires_in': 3600,
            u'id_token': u'token'}

        fake_user = {u'screen_name': u'johndoe',
                     u'user_id': u'11111'}

        self.register()
        self.signout()

        from pybossa.view import twitter
        response_user = twitter.manage_user(fake_response['access_token'],
                                            fake_user, None)

        assert response_user is None, response_user

    def test_41_password_change(self):
        """Test WEB password changing"""
        password = "mehpassword"
        self.register(password=password)
        res = self.app.post('/account/profile/password',
                            data={'current_password': password,
                                  'new_password': "p4ssw0rd",
                                  'confirm': "p4ssw0rd"},
                            follow_redirects=True)
        assert "Yay, you changed your password succesfully!" in res.data

        password = "mehpassword"
        self.register(password=password)
        res = self.app.post('/account/profile/password',
                            data={'current_password': "wrongpassword",
                                  'new_password': "p4ssw0rd",
                                  'confirm': "p4ssw0rd"},
                            follow_redirects=True)
        msg = "Your current password doesn't match the one in our records"
        assert msg in res.data

    def test_42_password_link(self):
        """Test WEB visibility of password change link"""
        self.register()
        res = self.app.get('/account/profile/settings')
        assert "Change your Password" in res.data
        user = model.User.query.get(1)
        user.twitter_user_id = 1234
        db.session.add(user)
        db.session.commit()
        res = self.app.get('/account/profile/settings')
        assert "Change your Password" not in res.data, res.data

    def test_43_terms_of_use_and_data(self):
        """Test WEB terms of use is working"""
        res = self.app.get('account/signin', follow_redirects=True)
        assert "/help/terms-of-use" in res.data, res.data
        assert "http://opendatacommons.org/licenses/by/" in res.data, res.data

        res = self.app.get('account/register', follow_redirects=True)
        assert "http://okfn.org/terms-of-use/" in res.data, res.data
        assert "http://opendatacommons.org/licenses/by/" in res.data, res.data

    @patch('pybossa.view.account.signer.loads')
    def test_44_password_reset_key_errors(self, Mock):
        """Test WEB password reset key errors are caught"""
        self.register()
        user = model.User.query.get(1)
        userdict = {'user': user.name, 'password': user.passwd_hash}
        fakeuserdict = {'user': user.name, 'password': 'wronghash'}
        key = signer.dumps(userdict, salt='password-reset')
        returns = [BadSignature('Fake Error'), BadSignature('Fake Error'), userdict,
                   fakeuserdict, userdict]

        def side_effects(*args, **kwargs):
            result = returns.pop(0)
            if isinstance(result, BadSignature):
                raise result
            return result
        Mock.side_effect = side_effects
        # Request with no key
        res = self.app.get('/account/reset-password', follow_redirects=True)
        assert 403 == res.status_code
        # Request with invalid key
        res = self.app.get('/account/reset-password?key=foo', follow_redirects=True)
        assert 403 == res.status_code
        # Request with key exception
        res = self.app.get('/account/reset-password?key=%s' % (key), follow_redirects=True)
        assert 403 == res.status_code
        res = self.app.get('/account/reset-password?key=%s' % (key), follow_redirects=True)
        assert 200 == res.status_code
        res = self.app.get('/account/reset-password?key=%s' % (key), follow_redirects=True)
        assert 403 == res.status_code
        res = self.app.post('/account/reset-password?key=%s' % (key),
                            data={'new_password': 'p4ssw0rD',
                                  'confirm': 'p4ssw0rD'},
                            follow_redirects=True)
        assert "You reset your password successfully!" in res.data

    def test_45_password_reset_link(self):
        """Test WEB password reset email form"""
        res = self.app.post('/account/forgot-password',
                            data={'email_addr': self.user.email_addr},
                            follow_redirects=True)
        assert ("We don't have this email in our records. You may have"
                " signed up with a different email or used Twitter, "
                "Facebook, or Google to sign-in") in res.data

        self.register()
        self.register(username='janedoe')
        jane = model.User.query.get(2)
        jane.twitter_user_id = 10
        db.session.add(jane)
        db.session.commit()
        with mail.record_messages() as outbox:
            self.app.post('/account/forgot-password',
                          data={'email_addr': self.user.email_addr},
                          follow_redirects=True)
            self.app.post('/account/forgot-password',
                          data={'email_addr': 'janedoe@example.com'},
                          follow_redirects=True)
            assert 'Click here to recover your account' in outbox[0].body
            assert 'your Twitter account to ' in outbox[1].body

    def test_46_task_presenter_editor_exists(self):
        """Test WEB task presenter editor is an option"""
        self.register()
        self.new_application()
        res = self.app.get('/app/sampleapp/tasks/', follow_redirects=True)
        assert "Edit the task presenter" in res.data, \
            "Task Presenter Editor should be an option"

    def test_47_task_presenter_editor_loads(self):
        """Test WEB task presenter editor loads"""
        self.register()
        self.new_application()
        res = self.app.get('/app/sampleapp/tasks/taskpresentereditor',
                           follow_redirects=True)
        err_msg = "Task Presenter options not found"
        assert "Task Presenter Editor" in res.data, err_msg
        err_msg = "Basic template not found"
        assert "The most basic template" in res.data, err_msg
        err_msg = "Image Pattern Recognition not found"
        assert "Flickr Person Finder template" in res.data, err_msg
        err_msg = "Geo-coding"
        assert "Urban Park template" in res.data, err_msg
        err_msg = "Transcribing documents"
        assert "PDF transcription template" in res.data, err_msg

    def test_48_task_presenter_editor_works(self):
        """Test WEB task presenter editor works"""
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        err_msg = "Task Presenter should be empty"
        assert not app.info.get('task_presenter'), err_msg

        res = self.app.get('/app/sampleapp/tasks/taskpresentereditor?template=basic',
                           follow_redirects=True)
        assert "var editor" in res.data, "CodeMirror Editor not found"
        assert "Task Presenter" in res.data, "CodeMirror Editor not found"
        assert "Task Presenter Preview" in res.data, "CodeMirror View not found"
        res = self.app.post('/app/sampleapp/tasks/taskpresentereditor',
                            data={'editor': 'Some HTML code!'},
                            follow_redirects=True)
        assert "Sample App" in res.data, "Does not return to app details"
        app = db.session.query(model.App).first()
        err_msg = "Task Presenter failed to update"
        assert app.info['task_presenter'] == 'Some HTML code!', err_msg

    @patch('pybossa.ckan.requests.get')
    def test_48_update_app_info(self, Mock):
        """Test WEB app update/edit works keeping previous info values"""
        html_request = FakeRequest(json.dumps(self.pkg_json_not_found), 200,
                                   {'content-type': 'application/json'})
        Mock.return_value = html_request

        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        err_msg = "Task Presenter should be empty"
        assert not app.info.get('task_presenter'), err_msg

        res = self.app.post('/app/sampleapp/tasks/taskpresentereditor',
                            data={'editor': 'Some HTML code!'},
                            follow_redirects=True)
        assert "Sample App" in res.data, "Does not return to app details"
        app = db.session.query(model.App).first()
        for i in range(10):
            key = "key_%s" % i
            app.info[key] = i
        db.session.add(app)
        db.session.commit()
        _info = app.info

        self.update_application()
        app = db.session.query(model.App).first()
        for key in _info:
            assert key in app.info.keys(), \
                "The key %s is lost and it should be here" % key
        assert app.name == "Sample App", "The app has not been updated"
        error_msg = "The app description has not been updated"
        assert app.description == "Description", error_msg
        error_msg = "The app icon has not been updated"
        assert app.info['thumbnail'] == "New Icon link", error_msg
        error_msg = "The app long description has not been updated"
        assert app.long_description == "Long desc", error_msg

    def test_49_announcement_messages(self):
        """Test WEB announcement messages works"""
        self.register()
        res = self.app.get("/", follow_redirects=True)
        error_msg = "There should be a message for the root user"
        assert "Root Message" in res.data, error_msg
        error_msg = "There should be a message for the user"
        assert "User Message" in res.data, error_msg
        error_msg = "There should not be an owner message"
        assert "Owner Message" not in res.data, error_msg
        # Now make the user an app owner
        self.new_application()
        res = self.app.get("/", follow_redirects=True)
        error_msg = "There should be a message for the root user"
        assert "Root Message" in res.data, error_msg
        error_msg = "There should be a message for the user"
        assert "User Message" in res.data, error_msg
        error_msg = "There should be an owner message"
        assert "Owner Message" in res.data, error_msg
        self.signout()

        # Register another user
        self.register(method="POST", fullname="Jane Doe", username="janedoe",
                      password="janedoe", password2="janedoe",
                      email="jane@jane.com")
        res = self.app.get("/", follow_redirects=True)
        error_msg = "There should not be a message for the root user"
        assert "Root Message" not in res.data, error_msg
        error_msg = "There should be a message for the user"
        assert "User Message" in res.data, error_msg
        error_msg = "There should not be an owner message"
        assert "Owner Message" not in res.data, error_msg
        self.signout()

        # Now as an anonymous user
        res = self.app.get("/", follow_redirects=True)
        error_msg = "There should not be a message for the root user"
        assert "Root Message" not in res.data, error_msg
        error_msg = "There should not be a message for the user"
        assert "User Message" not in res.data, error_msg
        error_msg = "There should not be an owner message"
        assert "Owner Message" not in res.data, error_msg

    def test_50_export_task_json(self):
        """Test WEB export Tasks to JSON works"""
        Fixtures.create()
        # First test for a non-existant app
        uri = '/app/somethingnotexists/tasks/export'
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        # Now get the tasks in JSON format
        uri = "/app/somethingnotexists/tasks/export?type=task&format=json"
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

        # Now with a real app
        uri = '/app/%s/tasks/export' % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        heading = "<strong>%s</strong>: Export All Tasks and Task Runs" % Fixtures.app_name
        assert heading in res.data, "Export page should be available\n %s" % res.data
        # Now test that a 404 is raised when an arg is invalid
        uri = "/app/%s/tasks/export?type=ask&format=json" % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        uri = "/app/%s/tasks/export?type=task&format=gson" % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        uri = "/app/%s/tasks/export?format=json" % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        uri = "/app/%s/tasks/export?type=task" % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

        # Now get the tasks in JSON format
        uri = "/app/%s/tasks/export?type=task&format=json" % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        exported_tasks = json.loads(res.data)
        app = db.session.query(model.App)\
                .filter_by(short_name=Fixtures.app_short_name)\
                .first()
        err_msg = "The number of exported tasks is different from App Tasks"
        assert len(exported_tasks) == len(app.tasks), err_msg

    def test_51_export_taskruns_json(self):
        """Test WEB export Task Runs to JSON works"""
        Fixtures.create()
        # First test for a non-existant app
        uri = '/app/somethingnotexists/tasks/export'
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        # Now get the tasks in JSON format
        uri = "/app/somethingnotexists/tasks/export?type=taskrun&format=json"
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

        # Now with a real app
        uri = '/app/%s/tasks/export' % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        heading = "<strong>%s</strong>: Export All Tasks and Task Runs" % Fixtures.app_name
        assert heading in res.data, "Export page should be available\n %s" % res.data
        # Now get the tasks in JSON format
        uri = "/app/%s/tasks/export?type=task_run&format=json" % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        exported_task_runs = json.loads(res.data)
        app = db.session.query(model.App)\
                .filter_by(short_name=Fixtures.app_short_name)\
                .first()
        err_msg = "The number of exported task runs is different from App Tasks"
        assert len(exported_task_runs) == len(app.task_runs), err_msg

    def test_52_export_task_csv(self):
        """Test WEB export Tasks to CSV works"""
        Fixtures.create()
        # First test for a non-existant app
        uri = '/app/somethingnotexists/tasks/export'
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        # Now get the tasks in JSON format
        uri = "/app/somethingnotexists/tasks/export?type=task&format=csv"
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

        # Now with a real app
        uri = '/app/%s/tasks/export' % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        heading = "<strong>%s</strong>: Export All Tasks and Task Runs" % Fixtures.app_name
        assert heading in res.data, "Export page should be available\n %s" % res.data
        # Now get the tasks in JSON format
        uri = "/app/%s/tasks/export?type=task&format=csv" % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        csv_content = StringIO.StringIO(res.data)
        csvreader = unicode_csv_reader(csv_content)
        app = db.session.query(model.App)\
                .filter_by(short_name=Fixtures.app_short_name)\
                .first()
        exported_tasks = []
        n = 0
        for row in csvreader:
            if n != 0:
                exported_tasks.append(row)
            n = n + 1
        err_msg = "The number of exported tasks is different from App Tasks"
        assert len(exported_tasks) == len(app.tasks), err_msg

    def test_53_export_task_runs_csv(self):
        """Test WEB export Task Runs to CSV works"""
        Fixtures.create()
        # First test for a non-existant app
        uri = '/app/somethingnotexists/tasks/export'
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status
        # Now get the tasks in JSON format
        uri = "/app/somethingnotexists/tasks/export?type=tas&format=csv"
        res = self.app.get(uri, follow_redirects=True)
        assert res.status == '404 NOT FOUND', res.status

        # Now with a real app
        uri = '/app/%s/tasks/export' % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        heading = "<strong>%s</strong>: Export All Tasks and Task Runs" % Fixtures.app_name
        assert heading in res.data, "Export page should be available\n %s" % res.data
        # Now get the tasks in JSON format
        uri = "/app/%s/tasks/export?type=task_run&format=csv" % Fixtures.app_short_name
        res = self.app.get(uri, follow_redirects=True)
        csv_content = StringIO.StringIO(res.data)
        csvreader = unicode_csv_reader(csv_content)
        app = db.session.query(model.App)\
                .filter_by(short_name=Fixtures.app_short_name)\
                .first()
        exported_task_runs = []
        n = 0
        for row in csvreader:
            if n != 0:
                exported_task_runs.append(row)
            n = n + 1
        err_msg = "The number of exported task runs is different \
                   from App Tasks Runs"
        assert len(exported_task_runs) == len(app.task_runs), err_msg

    def test_54_import_tasks(self):
        """Test WEB Import Tasks works"""
        # there's a bug in the test framework:
        # self.app.get somehow calls render_template twice
        return
        """Test WEB import Task templates should work"""
        self.register()
        self.new_application()
        # Without tasks, there should be a template
        res = self.app.get('/app/sampleapp/tasks/import', follow_redirects=True)
        err_msg = "There should be a CSV template"
        assert "template=csv" in res.data, err_msg
        err_msg = "There should be an Image template"
        assert "mode=image" in res.data, err_msg
        err_msg = "There should be a Map template"
        assert "mode=map" in res.data, err_msg
        err_msg = "There should be a PDF template"
        assert "mode=pdf" in res.data, err_msg
        # With tasks
        self.new_task(1)
        res = self.app.get('/app/sampleapp/tasks/import', follow_redirects=True)
        err_msg = "There should load directly the basic template"
        err_msg = "There should not be a CSV template"
        assert "template=basic" not in res.data, err_msg
        err_msg = "There should not be an Image template"
        assert "template=image" not in res.data, err_msg
        err_msg = "There should not be a Map template"
        assert "template=map" not in res.data, err_msg
        err_msg = "There should not be a PDF template"
        assert "template=pdf" not in res.data, err_msg

    def test_55_facebook_account_warning(self):
        """Test WEB Facebook OAuth user gets a hint to sign in"""
        user = model.User(fullname='John',
                          name='john',
                          email_addr='john@john.com',
                          info={})

        user.info = dict(facebook_token=u'facebook')
        msg, method = get_user_signup_method(user)
        err_msg = "Should return 'facebook' but returned %s" % method
        assert method == 'facebook', err_msg

        user.info = dict(google_token=u'google')
        msg, method = get_user_signup_method(user)
        err_msg = "Should return 'google' but returned %s" % method
        assert method == 'google', err_msg

        user.info = dict(twitter_token=u'twitter')
        msg, method = get_user_signup_method(user)
        err_msg = "Should return 'twitter' but returned %s" % method
        assert method == 'twitter', err_msg

        user.info = {}
        msg, method = get_user_signup_method(user)
        err_msg = "Should return 'local' but returned %s" % method
        assert method == 'local', err_msg

    def test_56_delete_tasks(self):
        """Test WEB delete tasks works"""
        Fixtures.create()
        # Anonymous user
        res = self.app.get('/app/test-app/tasks/delete', follow_redirects=True)
        err_msg = "Anonymous user should be redirected for authentication"
        assert "Please sign in to access this page" in res.data, err_msg
        err_msg = "Anonymous user should not be allowed to delete tasks"
        res = self.app.post('/app/test-app/tasks/delete', follow_redirects=True)
        err_msg = "Anonymous user should not be allowed to delete tasks"
        assert "Please sign in to access this page" in res.data, err_msg

        # Authenticated user but not owner
        self.register()
        res = self.app.get('/app/test-app/tasks/delete', follow_redirects=True)
        err_msg = "Authenticated user but not owner should get 403 FORBIDDEN in GET"
        assert res.status == '403 FORBIDDEN', err_msg
        res = self.app.post('/app/test-app/tasks/delete', follow_redirects=True)
        err_msg = "Authenticated user but not owner should get 403 FORBIDDEN in POST"
        assert res.status == '403 FORBIDDEN', err_msg
        self.signout()

        # Owner
        tasks = db.session.query(model.Task).filter_by(app_id=1).all()
        res = self.signin(email=u'tester@tester.com', password=u'tester')
        res = self.app.get('/app/test-app/tasks/delete', follow_redirects=True)
        err_msg = "Owner user should get 200 in GET"
        assert res.status == '200 OK', err_msg
        assert len(tasks) > 0, "len(app.tasks) > 0"
        res = self.app.post('/app/test-app/tasks/delete', follow_redirects=True)
        err_msg = "Owner should get 200 in POST"
        assert res.status == '200 OK', err_msg
        tasks = db.session.query(model.Task).filter_by(app_id=1).all()
        assert len(tasks) == 0, "len(app.tasks) != 0"

        # Admin
        res = self.signin(email=u'root@root.com', password=u'tester' + 'root')
        res = self.app.get('/app/test-app/tasks/delete', follow_redirects=True)
        err_msg = "Admin user should get 200 in GET"
        assert res.status_code == 200, err_msg
        res = self.app.post('/app/test-app/tasks/delete', follow_redirects=True)
        err_msg = "Admin should get 200 in POST"
        assert res.status_code == 200, err_msg

    def test_57_reset_api_key(self):
        """Test WEB reset api key works"""
        url = "/account/profile/resetapikey"
        # Anonymous user
        res = self.app.get(url, follow_redirects=True)
        err_msg = "Anonymous user should be redirected for authentication"
        assert "Please sign in to access this page" in res.data, err_msg
        res = self.app.post(url, follow_redirects=True)
        assert "Please sign in to access this page" in res.data, err_msg

        # Authenticated user
        self.register()
        user = db.session.query(model.User).get(1)
        api_key = user.api_key
        res = self.app.get(url, follow_redirects=True)
        err_msg = "Authenticated user should get access to reset api key page"
        assert res.status_code == 200, err_msg
        assert "Reset API Key" in res.data, err_msg
        res = self.app.post(url, follow_redirects=True)
        err_msg = "Authenticated user should be able to reset his api key"
        assert res.status_code == 200, err_msg
        user = db.session.query(model.User).get(1)
        err_msg = "New generated API key should be different from old one"
        assert api_key != user.api_key, err_msg

    def test_58_global_stats(self):
        """Test WEB global stats of the site works"""
        url = "/stats"
        res = self.app.get(url, follow_redirects=True)
        err_msg = "There should be a Global Statistics page of the project"
        assert "General Statistics" in res.data, err_msg

    def test_59_help_api(self):
        """Test WEB help api page exists"""
        Fixtures.create()
        url = "/help/api"
        res = self.app.get(url, follow_redirects=True)
        err_msg = "There should be a help api.html page"
        assert "API Help" in res.data, err_msg

    def test_69_allow_anonymous_contributors(self):
        """Test WEB allow anonymous contributors works"""
        Fixtures.create()
        app = db.session.query(model.App).first()
        url = '/app/%s/newtask' % app.short_name

        # All users are allowed to participate by default
        # As Anonymous user
        res = self.app.get(url, follow_redirects=True)
        err_msg = "The anonymous user should be able to participate"
        assert app.name in res.data, err_msg

        # As registered user
        self.register()
        self.signin()
        res = self.app.get(url, follow_redirects=True)
        err_msg = "The anonymous user should be able to participate"
        assert app.name in res.data, err_msg
        self.signout()

        # Now only allow authenticated users
        app.allow_anonymous_contributors = False
        db.session.add(app)
        db.session.commit()

        # As Anonymous user
        res = self.app.get(url, follow_redirects=True)
        err_msg = "User should be redirected to sign in"
        app = db.session.query(model.App).first()
        msg = "Oops! You have to sign in to participate in <strong>%s</strong>" % app.name
        assert msg in res.data, err_msg

        # As registered user
        res = self.signin()
        res = self.app.get(url, follow_redirects=True)
        err_msg = "The authenticated user should be able to participate"
        assert app.name in res.data, err_msg
        self.signout()

    def test_70_public_user_profile(self):
        """Test WEB public user profile works"""
        Fixtures.create()

        # Should work as an anonymous user
        url = '/account/%s/' % Fixtures.name
        res = self.app.get(url, follow_redirects=True)
        err_msg = "There should be a public profile page for the user"
        assert Fixtures.fullname in res.data, err_msg

        # Should work as an authenticated user
        self.signin()
        res = self.app.get(url, follow_redirects=True)
        assert Fixtures.fullname in res.data, err_msg

        # Should return 404 when a user does not exist
        url = '/account/a-fake-name-that-does-not-exist/'
        res = self.app.get(url, follow_redirects=True)
        err_msg = "It should return a 404"
        assert res.status_code == 404, err_msg

    @patch('pybossa.view.importer.requests.get')
    def test_71_bulk_epicollect_import_unauthorized(self, Mock):
        """Test WEB bulk import unauthorized works"""
        unauthorized_request = FakeRequest('Unauthorized', 403,
                                           {'content-type': 'application/json'})
        Mock.return_value = unauthorized_request
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        url = '/app/%s/tasks/import?template=csv' % (app.short_name)
        res = self.app.post(url, data={'epicollect_project': 'fakeproject',
                                       'epicollect_form': 'fakeform',
                                       'formtype': 'json'},
                            follow_redirects=True)
        msg = "Oops! It looks like you don't have permission to access the " \
              "EpiCollect Plus project"
        assert msg in res.data

    @patch('pybossa.view.importer.requests.get')
    def test_72_bulk_epicollect_import_non_html(self, Mock):
        """Test WEB bulk import non html works"""
        html_request = FakeRequest('Not an application/json', 200,
                                   {'content-type': 'text/html'})
        Mock.return_value = html_request
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        url = '/app/%s/tasks/import?template=csv' % (app.short_name)
        res = self.app.post(url, data={'epicollect_project': 'fakeproject',
                                       'epicollect_form': 'fakeform',
                                       'formtype': 'json'},
                            follow_redirects=True)
        msg = "Oops! That project and form do not look like the right one."
        assert msg in res.data

    @patch('pybossa.view.importer.requests.get')
    def test_73_bulk_epicollect_import_json(self, Mock):
        """Test WEB bulk import json works"""
        data = [dict(DeviceID=23)]
        html_request = FakeRequest(json.dumps(data), 200,
                                   {'content-type': 'application/json'})
        Mock.return_value = html_request
        self.register()
        self.new_application()
        app = db.session.query(model.App).first()
        res = self.app.post(('/app/%s/tasks/import' % (app.short_name)),
                            data={'epicollect_project': 'fakeproject',
                                  'epicollect_form': 'fakeform',
                                  'formtype': 'json'},
                            follow_redirects=True)

        app = db.session.query(model.App).first()
        err_msg = "Tasks should be imported"
        assert "1 Task imported successfully!" in res.data, err_msg
        tasks = db.session.query(model.Task).filter_by(app_id=app.id).all()
        err_msg = "The imported task from EpiCollect is wrong"
        assert tasks[0].info['DeviceID'] == 23, err_msg

        data = [dict(DeviceID=23), dict(DeviceID=24)]
        html_request = FakeRequest(json.dumps(data), 200,
                                   {'content-type': 'application/json'})
        Mock.return_value = html_request
        res = self.app.post(('/app/%s/tasks/import' % (app.short_name)),
                            data={'epicollect_project': 'fakeproject',
                                  'epicollect_form': 'fakeform',
                                  'formtype': 'json'},
                            follow_redirects=True)
        app = db.session.query(model.App).first()
        assert len(app.tasks) == 2, "There should be only 2 tasks"
        n = 0
        epi_tasks = [{u'DeviceID': 23}, {u'DeviceID': 24}]
        for t in app.tasks:
            assert t.info == epi_tasks[n], "The task info should be the same"
            n += 1

    def test_74_task_settings_page(self):
        """Test WEB TASK SETTINGS page works"""
        # Creat root user
        self.register()
        self.signout()
        # As owner
        self.register(fullname="owner", username="owner")
        self.new_application()
        url = "/app/%s/tasks/settings" % self.app_short_name

        res = self.app.get(url, follow_redirects=True)
        dom = BeautifulSoup(res.data)
        divs = ['task_scheduler', 'task_delete', 'task_redundancy']
        for div in divs:
            err_msg = "There should be a %s section" % div
            assert dom.find(id=div) is not None, err_msg

        self.signout()
        # As an authenticated user
        self.register(fullname="juan", username="juan")
        res = self.app.get(url, follow_redirects=True)
        err_msg = "User should not be allowed to access this page"
        assert res.status_code == 403, err_msg
        self.signout()

        # As an anonymous user
        res = self.app.get(url, follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "User should be redirected to sign in"
        assert dom.find(id="signin") is not None, err_msg

        # As root
        self.signin()
        res = self.app.get(url, follow_redirects=True)
        dom = BeautifulSoup(res.data)
        divs = ['task_scheduler', 'task_delete', 'task_redundancy']
        for div in divs:
            err_msg = "There should be a %s section" % div
            assert dom.find(id=div) is not None, err_msg

    def test_75_task_settings_scheduler(self):
        """Test WEB TASK SETTINGS scheduler page works"""
        # Creat root user
        self.register()
        self.signout()
        # Create owner
        self.register(fullname="owner", username="owner")
        self.new_application()
        url = "/app/%s/tasks/scheduler" % self.app_short_name
        form_id = 'task_scheduler'
        self.signout()

        # As owner and root
        for i in range(0, 1):
            if i == 0:
                # As owner
                self.signin(email="owner@example.com")
                sched = 'random'
            else:
                sched = 'default'
                self.signin()
            res = self.app.get(url, follow_redirects=True)
            dom = BeautifulSoup(res.data)
            err_msg = "There should be a %s section" % form_id
            assert dom.find(id=form_id) is not None, err_msg
            res = self.task_settings_scheduler(short_name=self.app_short_name,
                                               sched=sched)
            dom = BeautifulSoup(res.data)
            err_msg = "Task Scheduler should be updated"
            assert dom.find(id='msg_success') is not None, err_msg
            app = db.session.query(model.App).get(1)
            assert app.info['sched'] == sched, err_msg
            self.signout()

        # As an authenticated user
        self.register(fullname="juan", username="juan")
        res = self.app.get(url, follow_redirects=True)
        err_msg = "User should not be allowed to access this page"
        assert res.status_code == 401, err_msg
        self.signout()

        # As an anonymous user
        res = self.app.get(url, follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "User should be redirected to sign in"
        assert dom.find(id="signin") is not None, err_msg

    def test_76_task_settings_redundancy(self):
        """Test WEB TASK SETTINGS redundancy page works"""
        # Creat root user
        self.register()
        self.signout()
        # Create owner
        self.register(fullname="owner", username="owner")
        self.new_application()
        self.new_task(1)
        url = "/app/%s/tasks/redundancy" % self.app_short_name
        form_id = 'task_redundancy'
        self.signout()

        # As owner and root
        for i in range(0, 1):
            if i == 0:
                # As owner
                self.signin(email="owner@example.com")
                n_answers = 20
            else:
                n_answers = 10
                self.signin()
            res = self.app.get(url, follow_redirects=True)
            dom = BeautifulSoup(res.data)
            # Correct values
            err_msg = "There should be a %s section" % form_id
            assert dom.find(id=form_id) is not None, err_msg
            res = self.task_settings_redundancy(short_name=self.app_short_name,
                                                n_answers=n_answers)
            dom = BeautifulSoup(res.data)
            err_msg = "Task Redundancy should be updated"
            assert dom.find(id='msg_success') is not None, err_msg
            app = db.session.query(model.App).get(1)
            for t in app.tasks:
                assert t.n_answers == n_answers, err_msg
            # Wrong values, triggering the validators
            res = self.task_settings_redundancy(short_name=self.app_short_name,
                                                n_answers=0)
            dom = BeautifulSoup(res.data)
            err_msg = "Task Redundancy should be a value between 0 and 1000"
            assert dom.find(id='msg_error') is not None, err_msg
            res = self.task_settings_redundancy(short_name=self.app_short_name,
                                                n_answers=10000000)
            dom = BeautifulSoup(res.data)
            err_msg = "Task Redundancy should be a value between 0 and 1000"
            assert dom.find(id='msg_error') is not None, err_msg
            self.signout()

        # As an authenticated user
        self.register(fullname="juan", username="juan")
        res = self.app.get(url, follow_redirects=True)
        err_msg = "User should not be allowed to access this page"
        assert res.status_code == 401, err_msg
        self.signout()

        # As an anonymous user
        res = self.app.get(url, follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "User should be redirected to sign in"
        assert dom.find(id="signin") is not None, err_msg

    def test_77_task_settings_priority(self):
        """Test WEB TASK SETTINGS priority page works"""
        # Creat root user
        self.register()
        self.signout()
        # Create owner
        self.register(fullname="owner", username="owner")
        self.new_application()
        self.new_task(1)
        url = "/app/%s/tasks/priority" % self.app_short_name
        form_id = 'task_priority'
        self.signout()

        # As owner and root
        app = db.session.query(model.App).get(1)
        _id = app.tasks[0].id
        for i in range(0, 1):
            if i == 0:
                # As owner
                self.signin(email="owner@example.com")
                task_ids = str(_id)
                priority_0 = 1.0
            else:
                task_ids = "1"
                priority_0 = 0.5
                self.signin()
            res = self.app.get(url, follow_redirects=True)
            dom = BeautifulSoup(res.data)
            # Correct values
            err_msg = "There should be a %s section" % form_id
            assert dom.find(id=form_id) is not None, err_msg
            res = self.task_settings_priority(short_name=self.app_short_name,
                                              task_ids=task_ids,
                                              priority_0=priority_0)
            dom = BeautifulSoup(res.data)
            err_msg = "Task Priority should be updated"
            assert dom.find(id='msg_success') is not None, err_msg
            task = db.session.query(model.Task).get(_id)
            assert task.id == int(task_ids), err_msg
            assert task.priority_0 == priority_0, err_msg
            # Wrong values, triggering the validators
            res = self.task_settings_priority(short_name=self.app_short_name,
                                              priority_0=3,
                                              task_ids="1")
            dom = BeautifulSoup(res.data)
            err_msg = "Task Priority should be a value between 0.0 and 1.0"
            assert dom.find(id='msg_error') is not None, err_msg
            res = self.task_settings_priority(short_name=self.app_short_name,
                                              task_ids="1, 2")
            dom = BeautifulSoup(res.data)
            err_msg = "Task Priority task_ids should be a comma separated, no spaces, integers"
            assert dom.find(id='msg_error') is not None, err_msg
            res = self.task_settings_priority(short_name=self.app_short_name,
                                              task_ids="1,a")
            dom = BeautifulSoup(res.data)
            err_msg = "Task Priority task_ids should be a comma separated, no spaces, integers"
            assert dom.find(id='msg_error') is not None, err_msg

            self.signout()

        # As an authenticated user
        self.register(fullname="juan", username="juan")
        res = self.app.get(url, follow_redirects=True)
        err_msg = "User should not be allowed to access this page"
        assert res.status_code == 401, err_msg
        self.signout()

        # As an anonymous user
        res = self.app.get(url, follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "User should be redirected to sign in"
        assert dom.find(id="signin") is not None, err_msg

    def test_78_cookies_warning(self):
        """Test WEB cookies warning is displayed"""
        # As Anonymous
        res = self.app.get('/', follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "If cookies are not accepted, cookies banner should be shown"
        assert dom.find(id='cookies_warning') is not None, err_msg

        # As user
        self.signin(email=Fixtures.email_addr2, password=Fixtures.password)
        res = self.app.get('/', follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "If cookies are not accepted, cookies banner should be shown"
        assert dom.find(id='cookies_warning') is not None, err_msg
        self.signout()

        # As admin
        self.signin(email=Fixtures.root_addr, password=Fixtures.root_password)
        res = self.app.get('/', follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "If cookies are not accepted, cookies banner should be shown"
        assert dom.find(id='cookies_warning') is not None, err_msg
        self.signout()

    def test_49_cookies_warning2(self):
        """Test WEB cookies warning is hidden"""
        # As Anonymous
        self.app.set_cookie("localhost", "PyBossa_accept_cookies", "Yes")
        res = self.app.get('/', follow_redirects=True, headers={})
        dom = BeautifulSoup(res.data)
        err_msg = "If cookies are not accepted, cookies banner should be hidden"
        assert dom.find(id='cookies_warning') is None, err_msg

        # As user
        self.signin(email=Fixtures.email_addr2, password=Fixtures.password)
        res = self.app.get('/', follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "If cookies are not accepted, cookies banner should be hidden"
        assert dom.find(id='cookies_warning') is None, err_msg
        self.signout()

        # As admin
        self.signin(email=Fixtures.root_addr, password=Fixtures.root_password)
        res = self.app.get('/', follow_redirects=True)
        dom = BeautifulSoup(res.data)
        err_msg = "If cookies are not accepted, cookies banner should be hidden"
        assert dom.find(id='cookies_warning') is None, err_msg
        self.signout()
