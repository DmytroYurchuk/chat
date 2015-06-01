import logging
import tornado.ioloop
import tornado.web
import os.path
import tornado.escape
import uuid
import duckduckgo
import urllib2

from tornado.options import define, options, parse_command_line

define("port", default=8888, help="run on the given port", type=int)

class ChatBot(object):
    """Provides Bot for Chat"""
    def __init__(self):
        self.body = ""

    def get_body(self):
        return self.body

    def aid(self):
        self.body = ""
        self.body = "Sum of numbers: to_bot:sum(1, 1.5, 2, ....) \
                     Mean of numbers: to_bot:mean(1, 1.5, 2, ....) \
                     Search in duckduckgo.com: to_bot:duck(SearchPhrase) \
                     News from ycombinator.com: to_bot:news_y() "

    def sum_n(self):
        try:
            self.body = str(sum([float(i) for i in self.body.split(", ")]))
        except:
            self.body = "Incorrect sum format"

    def mean_n(self):
        try:
            temp = [float(i) for i in self.body.split(", ")]
            self.body = str(sum(temp) / len(temp))
        except:
            self.body = "Incorrect mean format"

    def duck_n(self):
        r = duckduckgo.query(self.body)
        self.body = ""
        for i in xrange(min(10, len(r.related))):
            self.body += r.related[i].url
            self.body += r.related[i].text
            self.body += " ***** "

    def news_n(self):
        self.body = "NEWS: "
        response = urllib2.urlopen('https://hacker-news.firebaseio.com/v0/newstories.json?print=pretty')
        base_url = 'https://hacker-news.firebaseio.com/v0/item/{}.json?print=pretty'
        newest_story_ids = tornado.escape.json_decode(response.read())
        for story in newest_story_ids[:10]:
            response = urllib2.urlopen(base_url.format(story))
            temp = tornado.escape.json_decode(response.read())
            self.body += temp["title"] + " " + temp["url"] + " ***** "        

    def execute(self, message):
        self.command = message.split("(")
        try:
            self.body = self.command[1][:-1]
            self.commands[self.command[0]](self)
        except:
            self.body = "Incorrect command"

    commands = {
        "help": aid,
        "sum": sum_n,
        "mean": mean_n,
        "duck": duck_n,
        "news_y": news_n,
    }
    

class MessageBuffer(object):
    """Provides buffer for messages"""
    def __init__(self):
        self.waiters = set()
        self.cache = []
        self.cache_size = 200

    def wait_for_messages(self, callback, cursor=None):
        if cursor:
            new_count = 0
            for msg in reversed(self.cache):
                if msg["id"] == cursor:
                    break
                new_count += 1
            if new_count:
                callback(self.cache[-new_count:])
                return
        self.waiters.add(callback)

    def cancel_wait(self, callback):
        self.waiters.remove(callback)

    def new_messages(self, messages):
        for callback in self.waiters:
            try:
                callback(messages)
            except:
                logging.error("Error in waiter callback", exc_info=True)
        self.waiters = set()
        self.cache.extend(messages)
        if len(self.cache) > self.cache_size:
            self.cache = self.cache[-self.cache_size:]


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user_json = self.get_secure_cookie("chat_user")
        if not user_json: return None
        return tornado.escape.json_decode(user_json)


class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("index.html", messages=self.application.message_buffer.cache)
          
        
class MessageNewHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        body = self.get_argument("body")
        user = self.current_user["name"]
        if body[:7] == "to_bot:":
            self.application.bot.execute(body[7:])
            body = self.application.bot.get_body()
            user = "from_bot"
        message = {
            "id": str(uuid.uuid4()),
            "from": user,
            "body": body,
        }
        message["html"] = self.render_string("message.html", message=message)
        if self.get_argument("next", None):
           self.redirect(self.get_argument("next"))
        else:
            self.write(message)
        if (message["from"] <> "from_bot") or (message["body"][:5] == "NEWS:"):
            self.application.message_buffer.new_messages([message])
            
            
class MessageUpdatesHandler(BaseHandler):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def post(self):
        cursor = self.get_argument("cursor", None)
        self.application.message_buffer.wait_for_messages(self.on_new_messages,cursor=cursor)
        
    def on_new_messages(self, messages):
        if self.request.connection.stream.closed():
            return
        self.finish(dict(messages=messages))

    def on_connection_close(self):
        self.application.message_buffer.cancel_wait(self.on_new_messages)   


class LoginHandler(BaseHandler):
    def get(self):
        self.render("login.html")
        
    def post(self):
        if self.get_argument("name", None):
           user = {"name": self.get_argument("name"),}
           test = self.set_secure_cookie("chat_user",tornado.escape.json_encode(user))
           self.redirect("/")
        else: self.redirect("/login")


class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("chat_user")
        self.redirect("/")
        

class Application(tornado.web.Application):
    """Main Class for this application holding everything together"""
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/login", LoginHandler),
            (r"/logout", LogoutHandler),
            (r"/message/new", MessageNewHandler),
            (r"/message/updates", MessageUpdatesHandler),
        ]
        settings = dict(
            cookie_secret = "43osdETzKXasdQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
            login_url = "/login",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies= True,
            autoreload=True,
        )
        tornado.web.Application.__init__(self, handlers, **settings)       
        self.message_buffer = MessageBuffer()
        self.bot = ChatBot()


def main():
    """Main function to run the chat"""
    parse_command_line()
    application = Application()
    application.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()





