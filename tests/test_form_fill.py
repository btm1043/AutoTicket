import unittest

from PyQt5.QtQml import QJSEngine
from PyQt5.QtWidgets import QApplication

from autoticket_app.models import FieldBinding, Ticket
from autoticket_app.servicenow import is_local_form_url, is_servicenow_url, build_ready_check_js, build_servicenow_fill_js


class FormFillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_configured_local_origin_is_allowed(self):
        pattern = r"service-now\.com"
        self.assertTrue(is_servicenow_url("https://127.0.0.1:8443/incident", pattern, "https://127.0.0.1:8443"))
        self.assertFalse(is_servicenow_url("https://127.0.0.1:8444/incident", pattern, "https://127.0.0.1:8443"))
        self.assertFalse(is_servicenow_url("https://other.example/incident", pattern, "https://127.0.0.1:8443"))

    def test_readiness_and_fill_in_nested_frame(self):
        engine = QJSEngine()
        engine.evaluate('''
          var field = {value: "", tagName: "INPUT", focus: function(){}, dispatchEvent: function(){}};
          var child = {document: {querySelector: function(s) {return s === "#summary" ? field : null;}},
                       frames: [], Event: function(){}};
          var window = {document: {querySelector: function(){return null;}}, frames: [child],
                        location: {href: "https://test.example/"}, title: "Test"};
          var document = window.document;
        ''')
        ready = engine.evaluate(build_ready_check_js("#summary"))
        self.assertFalse(ready.isError(), ready.toString())
        self.assertTrue(ready.toVariant()["ready"])
        result = engine.evaluate(build_servicenow_fill_js(
            Ticket(short_description="VPN issue"), (FieldBinding("short_description", "short_description", ("#summary",)),), "#summary"))
        self.assertFalse(result.isError(), result.toString())
        self.assertTrue(result.toVariant()["short_description"])
        self.assertEqual(engine.evaluate("field.value").toString(), "VPN issue")

    def test_missing_form_reports_error_without_write(self):
        engine = QJSEngine()
        engine.evaluate('var window = {document: {querySelector: function(){return null;}}, frames: []};')
        result = engine.evaluate(build_servicenow_fill_js(Ticket(), (), "#missing"))
        self.assertFalse(result.isError(), result.toString())
        self.assertIn("error", result.toVariant())

    def test_local_fields_without_form_ready_selector(self):
        engine = QJSEngine()
        engine.evaluate('''
          var field = {value: "", tagName: "INPUT", focus: function(){}, dispatchEvent: function(){}};
          var child = {document: {querySelector: function(s) {return s === "#summary" ? field : null;}},
                       frames: [], Event: function(){}};
          var window = {document: {querySelector: function(){return null;}}, frames: [child],
                        location: {href: "http://localhost:8443/"}, title: "Local"};
          var document = window.document;
        ''')
        bindings = (FieldBinding("short_description", "short_description", ("#summary",)),
                    FieldBinding("description", "description", ("#missing",)))
        self.assertFalse(engine.evaluate(build_ready_check_js("#no-form")).toVariant()["ready"])
        self.assertTrue(engine.evaluate(build_ready_check_js("#no-form", bindings, True)).toVariant()["ready"])
        result = engine.evaluate(build_servicenow_fill_js(Ticket(short_description="Local ticket"), bindings, "#no-form", True))
        self.assertFalse(result.isError(), result.toString())
        self.assertTrue(result.toVariant()["short_description"])
        self.assertFalse(result.toVariant()["description"])
        self.assertEqual(engine.evaluate("field.value").toString(), "Local ticket")
        self.assertFalse(engine.evaluate(build_ready_check_js("#no-form", bindings[1:], True)).toVariant()["ready"])

    def test_only_exact_local_hostnames_use_field_readiness(self):
        for url in ("http://localhost:8443/", "https://127.0.0.1/", "http://LOCALHOST/"):
            self.assertTrue(is_local_form_url(url))
        for url in ("https://localhost.example/", "https://127.0.0.1.example/", "https://service-now.com/", "file:///localhost"):
            self.assertFalse(is_local_form_url(url))
