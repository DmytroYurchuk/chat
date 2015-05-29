#!/usr/bin/env python

import logging
import tornado.escape
import tornado.ioloop
import tornado.web
import os.path
import uuid

from tornado.concurrent import Future
from tornado import gen
from tornado.options import define, options, parse_command_line

define("port", default=8888, help="run on the given port", type=int)
define("debug", default=False, help="run in debug mode")


class MessageBuffer(object):
    def __init__(self):
        self.waiters = set()
        self.cache = []
        self.cache_size = 200

    def wait_for_messages(self, cursor=None):
        # Construct a Future to return to our caller.  This allows
        # wait_for_messages to be yielded from a coroutine even though
        # it is not a coroutine itself.  We will set the result of the
        # Future when results are available.
        result_future = Future()
        if cursor:
            new_count = 0
            for msg in reversed(self.cache):
                if msg["id"] == cursor:
                    break
                new_count += 1
            if new_count:
                result_future.set_result(self.cache[-new_count:])
                return result_future
        self.waiters.add(result_future)
        return result_future

    def cancel_wait(self, future):
        self.waiters.remove(future)
        # Set an empty result to unblock any coroutines waiting.
        future.set_result([])

    def new_messages(self, messages):
        for future in self.waiters:
            future.set_result(messages)
        self.waiters = set()
        self.cache.extend(messages)
        if len(self.cache) > self.cache_size:
            self.cache = self.cache[-self.cache_size:]


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        args = dict(
            messages=self.application.message_buffer.cache,
            content='Enter your name and e-mail',
            user='',
        )
        self.render("index.html", **args)


class MessageNewHandler(tornado.web.RequestHandler):
    def post(self):
        body = self.get_argument("body")
        if body == "to_bot:help":
            message = {
                "id": str(uuid.uuid4()),
                "body": "from_bot: sum of numbers: to_bot:sum(1, 2, 3, ....)",
            }
        elif body[:10] == "to_bot:sum":
            message = {
                "id": str(uuid.uuid4()),
                "body": "from_bot: " + body[7:] + self.bot_sum(body[11:-1]),
            }
        else:
            message = {
                "id": str(uuid.uuid4()),
                "body": self.get_argument("user1") + ': ' + body,
            }
        message["html"] = tornado.escape.to_basestring(
            self.render_string("message.html", message=message))
        self.write(message)
        if body[:6] <> "to_bot":
            self.application.message_buffer.new_messages([message])
                
    def bot_sum(self, string_sum):
        try:
            return " = " + str(sum([float(i) for i in string_sum.split(", ")]))
        except:
            return " Incorrect format"
        

class MessageUpdatesHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def post(self):
        cursor = self.get_argument("cursor", None)
        self.future = self.application.message_buffer.wait_for_messages(cursor=cursor)
        messages = yield self.future
        if self.request.connection.stream.closed():
            return
        self.write(dict(messages=messages))

    def on_connection_close(self):
        self.application.message_buffer.cancel_wait(self.future)

class LoginHandler(tornado.web.RequestHandler):
    """
    Handler for login
    """
    def get(self):
        if self.get_argument("start_direct_auth", None):
            # Get form inputs.
            user = dict()
            user["email"] = self.get_argument("email", default="")
            user["name"] = self.get_argument("name", default="")
    
            # If user has not filled in all fields.
            if not user["email"] or not user["name"]:
                args = dict(
                    messages=self.application.message_buffer.cache,
                    content='Fill in both fields!',
                    user='',
                )
                self.render("index.html", **args)
                
            # All data given. Log user in!
            else:
                self.on_auth(user)
                
    def on_auth(self, user):
        """
        Callback for third party authentication (last step).
        """        
        if self.request.connection.stream.closed():
            logging.warning("Waiter disappeared")
            return
        args = dict(
            messages=self.application.message_buffer.cache,
            content='Enter your name and e-mail',
            user=user.get("name") or user.get("email"),
        )
        self.render("index.html", **args)

class Application(tornado.web.Application):
    """
    Main Class for this application holding everything together.
    """
    def __init__(self):

        # Handlers defining the url routing.
        handlers = [
            (r"/", MainHandler),
            (r"/login", LoginHandler),
            (r"/a/message/new", MessageNewHandler),
            (r"/a/message/updates", MessageUpdatesHandler),
        ]

        # Settings:
        settings = dict(
            cookie_secret = "13xsdETzKXasdTYRaYdTY56emGeJ89UeNhgQnp2XdTP1o/Vo=",
            login_url = "/login",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies= True,
            autoescape="xhtml_escape",
        )

        # Call super constructor.
        tornado.web.Application.__init__(self, handlers, **settings)

        #Buffer
        self.message_buffer = MessageBuffer()



def main():
    parse_command_line()
    application = Application()
    
    application.listen(options.port)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
