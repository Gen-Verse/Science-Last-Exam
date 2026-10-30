"""Guest entrypoint for the pinned controller, authenticated per QEMU instance."""
import hmac
import subprocess


def authorize(expected, header):
    return len(expected)>=24 and hmac.compare_digest(header,'Bearer '+expected)


def main():
    from main import app
    from flask import request, abort
    token=subprocess.check_output(['sudo','-n','cat',
        '/sys/firmware/qemu_fw_cfg/by_name/opt/scientific-software-operation/controller-token/raw'],text=True,timeout=5).strip()
    if len(token)<24:raise RuntimeError('Missing per-instance controller credential from QEMU fw_cfg')
    @app.before_request
    def authenticate():
        if not authorize(token,request.headers.get('Authorization','')):abort(403)
    app.run(host='0.0.0.0',port=5001,debug=False,threaded=True)


if __name__=='__main__':main()
