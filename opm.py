#!/usr/bin/env python3

import logging
import os
import subprocess
import xml.etree.ElementTree as ElementTree


class OpenNebula:

    ENV_ONEXMLRPC="ONE_XMLRPC"

    ONE_COMMANDS=["oneuser", "onevm"]

    @staticmethod
    def command_xml(name, *args):
        command = [name, *args, "--xml"]
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE)
        except Exception as e:
            raise Exception("Error while running command (reason : {0})".format(e))
        logging.debug(result.stdout)
        return result.stdout.decode()

    @classmethod
    def verify_environment(cls):
        endpoint = os.environ.get(cls.ENV_ONEXMLRPC)
        if endpoint is None:
            raise Exception(
                "Undefined environment variable {0}, define it with : "
                "export {0}=\"http://your_opennebula_host:2633/RPC2\""
                .format(cls.ENV_ONEXMLRPC))
        else:
            logging.info("Using {0}={1} to commicate with OpenNebula"
                .format(cls.ENV_ONEXMLRPC, endpoint))

    @classmethod
    def verify_commands(cls):
        for command in cls.ONE_COMMANDS:
            retult = None
            try:
                result = subprocess.run(
                    [command, "--version"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL)
            except Exception as e:
                raise Exception("Error while running command (reason : {0})".format(command, e))
            logging.info("Command '{0}' found, returned {1}".format(command, result.returncode))

    def set_user_info(self):
        try:
            result = self.command_xml("oneuser", "show")
        except Exception as e:
            raise Exception("Error while running command, try to log "
                "in using `oneuser login your_user_name --force` "
                "first (reason : {0})".format(e))
        logging.info("User has a valid authorization token")
        logging.debug("User has a valid authorization token")
        root = ElementTree.fromstring(result)
        self.uid = int(root.find("ID").text)
        self.gid = int(root.find("GID").text)
        logging.debug("uid={0} gid={0}".format(self.uid, self.gid))

    def list_vm(self):
        try:
            result = self.command_xml("onevm", "list")
        except Exception as e:
            raise Exception("Error while running command (reason : {0})".format(e))
        root = ElementTree.fromstring(result)
        for vm_elem in root.findall("VM"):
            ElementTree.dump(vm_elem)

    def __init__(self):
        self.set_user_info()


class App:

    def __init__(self, args):
        self.args = args
        self.setup_logging()
        OpenNebula.verify_environment()
        OpenNebula.verify_commands()
        self.one = OpenNebula()

    def setup_logging(self):
        # root logger
        numeric_level = getattr(logging, self.args.log_level.upper())
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)
        # format
        log_format = "%(message)s"
        if numeric_level == logging.DEBUG:
            log_format = " ".join([
                "thread=%(threadName)s",
                "module=%(module)s",
                "func=%(funcName)s",
                "line=%(lineno)d",
                ": {0}"]).format(log_format)
        # logging output
        handler = logging.StreamHandler()
        log_format = "%(asctime)s %(levelname)s {0}".format(log_format)
        # finalize
        formatter = logging.Formatter(log_format)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
        logging.debug("Command line arguments: {0}".format(args))

    def run(self):
        vms = self.one.list_vm()

if __name__ == '__main__':

    import argparse
    import sys

    try:
        parser = argparse.ArgumentParser(description="one-pf-manage")
        parser.add_argument("-l",
                            "--log-level",
                            metavar="LVL",
                            choices=[
                                "critical",
                                "error",
                                "warning",
                                "info",
                                "debug"],
                            default="warning")
        parser.add_argument("action",
                            choices=[
                                "create",
                                "update",
                                "destroy"])
        parser.add_argument("jsonfile")

        args = parser.parse_args()

        app = App(args)
        app.run()

        sys.exit(0)

    except KeyboardInterrupt as e:
        logging.warning("Caught SIGINT (Ctrl-C), exiting.")
        sys.exit(1)

    except SystemExit as e:
        message = "Exiting with return code {0}".format(e.code)
        if e.code == 0:
            logging.info(message)
        else:
            logging.warn(message)
            raise e

    except Exception as e:
        logging.critical("{0}: {1}".format(e.__class__.__name__, e))
        # when debugging, we want the stack-trace
        if args.log_level == "debug":
            raise e
