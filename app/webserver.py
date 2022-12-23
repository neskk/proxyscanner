from flask import Flask, Response, request, render_template, jsonify, send_file
import logging
import sys

from flask_app import utils
from flask_app.config import Config
from flask_app.models import init_database

log = logging.getLogger(__name__)

# https://flask.palletsprojects.com/en/2.0.x/api/
app = Flask(__name__,
            static_url_path='',
            static_folder='static',
            template_folder='templates')
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
    return render_template('page.html', data=request.headers)


@app.route('/get_data.json')
def get_data():
    data = db.query('')
    return jsonify(data)


@app.route('/get_image')
def get_image():
    filepath = db.query('')

    return send_file(filepath, mimetype='image/jpeg')


def check_configuration(args):
    if args.max_concurrency <= 0:
        log.error('Max concurrency argument must be higher than 0.')
        sys.exit(1)

    if args.notice_interval <= 0:
        log.error('Notice interval must be higher than 0.')
        sys.exit(1)

    if args.protocol == 'all':
        # faster performance
        args.protocol = None


def cleanup():
    """ Handle shutdown tasks """
    log.info('Shutting down...')


if __name__ == '__main__':
    try:
        args = Config.get_args()
        utils.configure_logging(args, log)
        db = init_database(
            args.db_name, args.db_host, args.db_port, args.db_user, args.db_pass)

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
