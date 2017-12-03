#!/usr/bin/env python3

import json
import logging
import os
import re
import subprocess
import xml.etree.ElementTree as ElementTree


class VmInfo:

    @staticmethod
    def fromOneXml(vm_xml):
        # ElementTree.dump(vm_xml)
        vcpu = vm_xml.find("TEMPLATE/VCPU")
        if vcpu is None:
            vcpu = 1
        else:
            vcpu = int(vcpu.text)
        networks = [ x.text for x in vm_xml.findall("TEMPLATE/NIC/NETWORK") ]
        return VmInfo(
            int(vm_xml.find("ID").text),
            vm_xml.find("NAME").text,
            int(vm_xml.find("STATE").text),
            float(vm_xml.find("TEMPLATE/CPU").text),
            vcpu,
            vm_xml.find("TEMPLATE/DISK/IMAGE").text,
            int(vm_xml.find("TEMPLATE/MEMORY").text),
            networks)

    @staticmethod
    def fromJsonDefinition(vm_name, vm_json_template):
        return VmInfo(
            None,
            vm_name,
            None,
            vm_json_template['cpu_percent'],
            vm_json_template['vcpu_count'],
            vm_json_template['image'],
            vm_json_template['mem_mb'],
            vm_json_template['networks'])

    def __init__(self, vm_id, name, state, cpu, vcpu, image, mem_mb, networks):
        self.id = vm_id
        self.name = name
        self.state = state
        self.cpu = cpu
        self.vcpu = vcpu
        self.image = image
        self.mem_mb = mem_mb
        self.networks = networks

    def __repr__(self):
        return "VmInfo[id={0}, name={1}, state={2}, cpu={3}, vcpu={4}, image={5}, mem_mb={6}, networks={7}]".format(self.id, self.name, self.state, self.cpu, self.vcpu, self.image, self.mem_mb, self.networks)


class OpenNebula:

    ENV_ONEXMLRPC="ONE_XMLRPC"

    ONE_COMMANDS=["oneuser", "onevm"]

    @staticmethod
    def command(name, *args):
        command = [name, *args]
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        except Exception as e:
            raise Exception("Error while running command {0} (reason : {1})".format(command, e))
        if result.returncode != 0:
            raise Exception("Error while running command {0} (return code : {1}, stdout: {2}, stderr: {3})".format(command, result.returncode, result.stdout, result.stderr))
        logging.debug("STDOUT: {0}".format(result.stdout))
        return result.stdout.decode()

    @classmethod
    def verify_environment(cls):
        endpoint = os.environ.get(cls.ENV_ONEXMLRPC)
        if endpoint is None:
            raise Exception("Undefined environment variable {0}, define it with : export {0}=\"http://your_opennebula_host:2633/RPC2\"".format(cls.ENV_ONEXMLRPC))
        else:
            logging.info("Using {0}={1} to commicate with OpenNebula".format(cls.ENV_ONEXMLRPC, endpoint))

    @classmethod
    def verify_commands(cls):
        for command in cls.ONE_COMMANDS:
            retult = None
            try:
                result = subprocess.run([command, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            except Exception as e:
                raise Exception("Error while running command (reason : {0})".format(command, e))
            logging.debug("Command '{0}' found, returned {1}".format(command, result.returncode))

    def set_user_info(self):
        try:
            result = self.command("oneuser", "show", "--xml")
        except Exception as e:
            raise Exception("Error while running command, try to log in using `oneuser login your_user_name --force` first (reason : {0})".format(e))
        root = ElementTree.fromstring(result)
        self.uid = int(root.find("ID").text)
        self.gid = int(root.find("GID").text)
        logging.info("User has a valid authorization token (uid={0} gid={0})".format(self.uid, self.gid))

    def vm_list(self):
        vms = {}
        try:
            result = self.command("onevm", "list", "--xml")
        except Exception as e:
            raise Exception("Error while running command (reason : {0})".format(e))
        root = ElementTree.fromstring(result)
        # ElementTree.dump(root)
        for vm_elem in root.findall("VM"):
            vm = VmInfo.fromOneXml(vm_elem)
            vms[vm.name] = vm
        logging.debug("VM list: {0}".format(vms))
        return vms

    def vm_create(self, vm_info):
        logging.debug("Creating vm: {0}".format(vm_info))
        args = ["--name", vm_info.name,
                "--cpu", str(vm_info.cpu),
                "--vcpu", str(vm_info.vcpu),
                "--memory", "{0}m".format(vm_info.mem_mb),
                "--disk", vm_info.image]
        if len(vm_info.networks) > 0:
            args.append("--nic")
            args.append(",".join(vm_info.networks))
        try:
            result = self.command("onevm", "create", *args)
        except Exception as e:
            raise Exception("Error while running command (reason : {0})".format(e))
        # store vm id number
        m = re.search(r'^ID: (\d+)$', result)
        if not m:
            raise Exception("Could not detect VM id after creation")
        vm_info.id = int(m.group(1))

    def vm_destroy(self, vm_info):
        logging.debug("Destroying vm: {0}".format(vm_info))
        try:
            result = self.command("onevm", "delete", str(vm_info.id))
        except Exception as e:
            raise Exception("Error while running command (reason : {0})".format(e))

    def __init__(self):
        self.set_user_info()


class App:

    def __init__(self, args):
        self.args = args
        self.setup_logging()
        self.target = self.load(args.jsonfile)
        self.existing = {}
        logging.debug("VM definitions: {0}".format(self.target))
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

    def load_v1(self, jdata):
        defs = {}
        for vm_name, template_name in jdata['hosts'].items():
            full_name = "{0}-{1}".format(jdata['platformName'], vm_name)
            defs[full_name] = VmInfo.fromJsonDefinition(full_name, jdata['templates'][template_name])
        logging.debug("Definitions: {0}".format(defs))
        return defs

    def load(self, jsonfile):
        with open(self.args.jsonfile) as fileobj:
            j = json.load(fileobj)
            self.platformName = j['platformName']
            if int(j['formatVersion']) == 1:
                return self.load_v1(j)
            raise Exception("Unhandled format {0}".format(j['formatVersion']))

    def create(self, vm_name):
        logging.warning("VM {0} does not exist, creating it".format(vm_name))
        vm = self.target[vm_name]
        self.one.vm_create(vm)
        logging.info("Created VM with ID {0}".format(vm.id))

    def verify(self, vm_name):
        logging.info("Verifying VM {0}".format(vm_name))

    def destroy(self, vm_name):
        logging.warning("Destroying unreferenced VM {0}".format(vm_name))
        vm = self.existing[vm_name]
        self.one.vm_destroy(vm)
        logging.info("Destroyed VM with ID {0}".format(vm.id))

    def list(self, platformName):
        vms = self.one.vm_list()
        # ignoring VM without our prefix
        vms = {
            key:value for key, value in vms.items()
            if value.name.startswith("{0}-".format(platformName))
        }
        logging.debug("Filtered VM {0}".format(vms))
        return vms

    def run(self):
        # get existing vm for our platform
        self.existing = self.list(self.platformName)
        # compute sets for actions
        current = set(self.existing.keys())
        target = set(self.target.keys())
        # create what must be created
        for vm_name in target.difference(current):
            self.create(vm_name)
        # verify what could differ
        for vm_name in target.intersection(current):
            self.verify(vm_name)
        # delete what should not be there
        for vm_name in current.difference(target):
            self.destroy(vm_name)


if __name__ == '__main__':

    import argparse
    import sys

    try:
        parser = argparse.ArgumentParser(description="one-pf-manage")
        parser.add_argument("-l", "--log-level", metavar="LVL", choices=["critical", "error", "warning", "info", "debug"], default="warning")
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
