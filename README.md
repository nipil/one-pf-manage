# one-pf-manage

Simple platform management scripts using opennebul cli

# objective

Describe a bunch of VM with an expressive and flexible DRY json structure, and do scripted operations (create/delete/check) based on that description

# install

Python 3 script, uses standard modules only : `json`, `logging`, `os`, `re`, `subprocess`, `xml.etree.ElementTree`

Requires OpenNebula CLI tools (`oneuser`, `onevm` and `onetemplate`) for which you can read the [official installation instructions](https://docs.opennebula.org/5.4/deployment/opennebula_installation/frontend_installation.html).

Tested with OpenNebula [virtual sandbox](https://opennebula.org/tryout/sandboxvirtualbox/) (using version `5.4`)

# how does it work

An exemple is provided in the `docs` folder.

The principle is the following :

- the `platform_name` defines the prefix for all VM name. It *CANNOT* be empty, or every accessible VM in OpenNebula would be considered part of the platform.
- the `hosts` element lists all desired VMs ; each VM name will be prefixed with `platform_name`, followed by a dash `-`, followed by the host name

Each host has a "desired" configuration, based on a succession of overrides, with the following precedence :

- initial configuration is read from `defaults`
- if the host references a `class`, the configuration is updated with the overrides defined in given class
- the configuration is finally updated with the eventual overrides found in the given host definition

With the following JSON content :

    {
        "format_version":"3",
        "platform_name":"project-version",
        "defaults":{
            "one_template": null,
            "cpu_percent": 0.1,
            "vcpu_count": 1,
            "mem_mb": 128,
            "disks": [{
            "image": "ttylinux",
            "size_mb": 256
            }],
            "networks":["cloud"]
        },
        "classes":{
            "more_mem":{ "mem_mb": 512 },
            "with_template":{ "one_template": "ttylinux" },
            "recursive":{ "class": "more_mem" }
        },
        "hosts":{
            "srv1":{
                "class": "more_mem",
                "mem_mb": 384,
                "networks":[]
            },
            "srv2":{ "class": "with_template" },
            "srv3":{ "vcpu_count": 2 },
            "srv4":{},
            "srv5":{
                "mem_mb": 384,
                "class": "recursive"
            }
        }
    }

This yields the following target configurations :

    name: project-version-srv1
        cpu: 0.1
        vcpu: 1
        mem_mb: 384
        one_template: None
        networks: 0
        disks: 1
            image ttylinux of size 256 Mbytes
    name: project-version-srv2
        cpu: 0.1
        vcpu: 1
        mem_mb: 128
        one_template: ttylinux
        networks: 1
            cloud
        disks: 1
            image ttylinux of size 256 Mbytes
    name: project-version-srv3
        cpu: 0.1
        vcpu: 2
        mem_mb: 128
        one_template: None
        networks: 1
            cloud
        disks: 1
            image ttylinux of size 256 Mbytes
    name: project-version-srv4
        cpu: 0.1
        vcpu: 1
        mem_mb: 128
        one_template: None
        networks: 1
            cloud
        disks: 1
            image ttylinux of size 256 Mbytes
    name: project-version-srv5
        cpu: 0.1
        vcpu: 1
        mem_mb: 384
        one_template: None
        networks: 1
            cloud
        disks: 1
            image ttylinux of size 256 Mbytes

As you can see :

- the vm name uses the platform name as prefix
- `project-version-srv5` classes are applied depth-first
- `project-version-srv4` has no overrides at all and equals `default`
- `project-version-srv3` had only a host override for `vcpu`
- `project-version-srv2` had only a class override for `one_template`
- `project-version-srv1` had both a class and a host override both modifying `mem_mb` and its final value respects precedence, and a host override for the network.

# pre-requisites

As this tool uses the standard OpenNebula CLI, your environment variables `ONE_XMLRPC` *must* be configured appropriately, for use by the CLI tools.

You *must* pre-log into your OpenNebula cluster using the CLI tools (eventually defining `ONE_AUTH` and using `oneuser`) before running the provided script

# usage

The `-h` option displays available command-line options.

You can start your json template, using `docs/example.json` and the above explanation as an example.

In case you have trouble or wonder what gets parsed out of your description, you can use the `parse-only` option.

Then you run `./opm.py yourfile.json` (the default operation is `status`).

For the example configuration, this yields :

    $ ./opm.py docs/example.json status
    project-version-srv1: missing
    project-version-srv2: missing
    project-version-srv3: missing
    project-version-srv4: missing
    project-version-srv5: missing
    project-version-srv6: missing
    project-version-srv7: missing

This means that the VM are not created. You can create them :

    $ ./opm.py docs/example.json create-missing
    project-version-srv1: created ID 43
    project-version-srv2: created ID 44
    project-version-srv3: created ID 45
    project-version-srv4: created ID 46
    project-version-srv5: created ID 47
    project-version-srv6: created ID 48
    project-version-srv7: created ID 49

*Note* : each VM is created on hold to allow for possible `pxe` boot menu. As a consequence, each VM must be released before it starts running. See your OpenNebula documentation for `hold`/`release` operations.

If you then add another host `srv8` into the file, and run `status` :

    $ ./opm.py docs/example.json status
    project-version-srv8: missing
    project-version-srv1: present ID 43
    project-version-srv2: present ID 44
    project-version-srv3: present ID 45
    project-version-srv4: present ID 46
    project-version-srv5: present ID 47
    project-version-srv6: present ID 48
    project-version-srv7: present ID 49

You can create the missing VM with the same creation command :

    $ ./opm.py docs/example.json create-missing
    project-version-srv8: created ID 50

If you remove a devinition from your file, and run status again :

    $ ./opm.py docs/example.json
    project-version-srv1: present ID 43
    project-version-srv2: present ID 44
    project-version-srv3: present ID 45
    project-version-srv4: present ID 46
    project-version-srv5: present ID 47
    project-version-srv7: present ID 49
    project-version-srv8: present ID 50
    project-version-srv6: unreferenced ID 48

You can remove the unreferenced VM using `delete-unreferenced`

    $ ./opm.py docs/example.json delete-unreferenced
    project-version-srv6: destroyed ID 48

If you update a definition in the json file, and run `verify-present`

    $ ./opm.py docs/example.json verify-present
    project-version-srv4: ID 46, existing vcpu must change from 4 to 3

*Note*: `verify-present` outputs a `WARNING` about "not yet implemented" disk comparison, but every other configuration element is checked for differences

*Note*: in the future, the configuration differences might be applied automatically, if the VM is in the appropriate state.

Finally, you can remove all (existing) platform vm using `delete-all`

    $ ./opm.py docs/example.json delete-all
    project-version-srv1: destroyed ID 43
    project-version-srv2: destroyed ID 44
    project-version-srv3: destroyed ID 45
    project-version-srv4: destroyed ID 46
    project-version-srv5: destroyed ID 47
    project-version-srv7: destroyed ID 49
    project-version-srv8: destroyed ID 50

And _voilà_.
