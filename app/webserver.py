from flask import Flask, Response, request, abort, render_template, jsonify, send_file
import logging
import sys

from proxytools.config import Config
from proxytools.models import init_database, ProxyProtocol, ProxyStatus, Proxy, ProxyTest
from proxytools.utils import configure_logging

log = logging.getLogger(__name__)

# https://flask.palletsprojects.com/en/2.0.x/api/
app = Flask(__name__,
            static_url_path='',
            static_folder='static',
            template_folder='templates')

app.config['JSON_SORT_KEYS'] = False
args = None
db = None


@app.before_request
def before_request():
    db.connect()


@app.after_request
def after_request(response):
    db.close()
    return response


# Flask webserver routes
@app.route('/')
def index():
    stats = {
        'Proxy count': Proxy.select().count(),
        'Test count': ProxyTest.select().count(),
    }
    return render_template('page.html', data=stats)


@app.route('/azenv')
def azenv():
    return render_template('azenv.html', data=request.headers)


@app.route('/proxydata')
def proxydata():
    protocol = request.args.get('protocol', None)
    limit = int(request.args.get('limit', 100))
    max_age = int(request.args.get('max_age', 3600))
    exclude_countries = request.args.get('exclude_countries', [])

    if limit > 1000:
        limit = 1000
    if max_age > 86400:
        max_age = 86400

    if protocol:
        protocol = ProxyProtocol[protocol.upper()]

    if exclude_countries:
        exclude_countries = exclude_countries.split(',')

    query = Proxy.get_valid(
        limit,
        max_age,
        protocol,
        exclude_countries)

    data = [proxy.data() for proxy in query.execute()]

    return jsonify(data)


@app.route('/proxylist')
def proxylist():
    protocol = request.args.get('protocol', None)
    limit = int(request.args.get('limit', 100))
    max_age = int(request.args.get('max_age', 3600))
    exclude_countries = request.args.get('exclude_countries', [])

    if limit > 1000:
        limit = 1000
    if max_age > 86400:
        max_age = 86400

    if protocol:
        protocol = ProxyProtocol[protocol.upper()]

    if exclude_countries:
        exclude_countries = exclude_countries.split(',')

    query = Proxy.get_valid(
        limit,
        max_age,
        protocol,
        exclude_countries)

    data = [proxy.url() for proxy in query.execute()]

    return jsonify(data)


@app.route('/proxy/<id>')
def proxy(id):

    if not id:
        abort(400)

    proxy = Proxy.get(id)
    if not proxy:
        abort(400)

    return jsonify(proxy.test_score())


@app.route('/get_image')
def get_image():
    filepath = db.query('')

    return send_file(filepath, mimetype='image/jpeg')


def cleanup():
    """ Handle shutdown tasks """
    log.info('Shutting down...')


if __name__ == '__main__':
    try:
        args = Config.get_args()
        configure_logging(log, args.verbose, args.log_path, "-webserver")

        db = init_database(
            args.db_name,
            args.db_host,
            args.db_port,
            args.db_user,
            args.db_pass)

        log.info('Starting up...')
        # Note: Flask reloader runs two processes
        # https://stackoverflow.com/questions/25504149/why-does-running-the-flask-dev-server-run-itself-twice
        app.run(
            debug=True if args.verbose else False,
            host='0.0.0.0',
            port=5000,
            use_reloader=False)
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        log.exception(e)
    finally:
        cleanup()
        sys.exit()
