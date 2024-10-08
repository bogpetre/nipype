"""This script generates Slicer Interfaces based on the CLI modules XML. CLI
modules are selected from the hardcoded list below and generated code is placed
in the cli_modules.py file (and imported in __init__.py). For this to work
correctly you must have your CLI executables in $PATH"""

import xml.dom.minidom
import subprocess
import os
from shutil import rmtree

import keyword

python_keywords = (
    keyword.kwlist
)  # If c++ SEM module uses one of these key words as a command line parameter, we need to modify variable


def force_to_valid_python_variable_name(old_name):
    """Valid c++ names are not always valid in python, so
    provide alternate naming

    >>> force_to_valid_python_variable_name('lambda')
    'opt_lambda'
    >>> force_to_valid_python_variable_name('inputVolume')
    'inputVolume'
    """
    new_name = old_name
    new_name = new_name.lstrip().rstrip()
    if old_name in python_keywords:
        new_name = "opt_" + old_name
    return new_name


def add_class_to_package(class_codes, class_names, module_name, package_dir):
    module_python_filename = os.path.join(package_dir, "%s.py" % module_name)
    with open(module_python_filename, "w") as f_m:
        f_m.write(
            """# -*- coding: utf-8 -*-
\"\"\"Autogenerated file - DO NOT EDIT
If you spot a bug, please report it on the mailing list and/or change the generator.\"\"\"\n\n"""
        )
        imports = """\
from ..base import (CommandLine, CommandLineInputSpec, SEMLikeCommandLine, TraitedSpec,
                    File, Directory, traits, isdefined, InputMultiPath, OutputMultiPath)
import os\n\n\n"""
        f_m.write(imports)
        f_m.write("\n\n".join(class_codes))
    with open(os.path.join(package_dir, "__init__.py"), "a+") as f_i:
        f_i.write("from {} import {}\n".format(module_name, ", ".join(class_names)))


def crawl_code_struct(code_struct, package_dir):
    subpackages = []
    for k, v in code_struct.items():
        if isinstance(v, (str, bytes)):
            module_name = k.lower()
            class_name = k
            class_code = v
            add_class_to_package([class_code], [class_name], module_name, package_dir)
        else:
            l1 = {}
            l2 = {}
            for key in list(v.keys()):
                if isinstance(v[key], (str, bytes)):
                    l1[key] = v[key]
                else:
                    l2[key] = v[key]
            if l2:
                v = l2
                subpackages.append(k.lower())
                with open(os.path.join(package_dir, "__init__.py"), "a+") as f_i:
                    f_i.write("from %s import *\n" % k.lower())
                new_pkg_dir = os.path.join(package_dir, k.lower())
                if os.path.exists(new_pkg_dir):
                    rmtree(new_pkg_dir)
                os.mkdir(new_pkg_dir)
                crawl_code_struct(v, new_pkg_dir)
                if l1:
                    for ik, iv in l1.items():
                        crawl_code_struct({ik: {ik: iv}}, new_pkg_dir)
            elif l1:
                v = l1
                module_name = k.lower()
                add_class_to_package(
                    list(v.values()), list(v.keys()), module_name, package_dir
                )
        if subpackages:
            with open(os.path.join(package_dir, "setup.py"), "w") as f:
                f.write(
                    """# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
def configuration(parent_package='',top_path=None):
    from numpy.distutils.misc_util import Configuration

    config = Configuration('{pkg_name}', parent_package, top_path)

    {sub_pks}

    return config

if __name__ == '__main__':
    from numpy.distutils.core import setup
    setup(**configuration(top_path='').todict())
""".format(
                        pkg_name=package_dir.split("/")[-1],
                        sub_pks="\n    ".join(
                            [
                                "config.add_data_dir('%s')" % sub_pkg
                                for sub_pkg in subpackages
                            ]
                        ),
                    )
                )


def generate_all_classes(
    modules_list=[], launcher=[], redirect_x=False, mipav_hacks=False
):
    """modules_list contains all the SEM compliant tools that should have wrappers created for them.
    launcher containtains the command line prefix wrapper arguments needed to prepare
    a proper environment for each of the modules.
    """
    all_code = {}
    for module in modules_list:
        print("=" * 80)
        print(f"Generating Definition for module {module}")
        print("^" * 80)
        package, code, module = generate_class(
            module, launcher, redirect_x=redirect_x, mipav_hacks=mipav_hacks
        )
        cur_package = all_code
        module_name = package.strip().split(" ")[0].split(".")[-1]
        for package in package.strip().split(" ")[0].split(".")[:-1]:
            if package not in cur_package:
                cur_package[package] = {}
            cur_package = cur_package[package]
        if module_name not in cur_package:
            cur_package[module_name] = {}
        cur_package[module_name][module] = code
    if os.path.exists("__init__.py"):
        os.unlink("__init__.py")
    crawl_code_struct(all_code, os.getcwd())


def generate_class(
    module, launcher, strip_module_name_prefix=True, redirect_x=False, mipav_hacks=False
):
    dom = grab_xml(module, launcher, mipav_hacks=mipav_hacks)
    if strip_module_name_prefix:
        module_name = module.split(".")[-1]
    else:
        module_name = module
    inputTraits = []
    outputTraits = []
    outputs_filenames = {}

    # self._outputs_nodes = []

    class_string = '"""'

    for desc_str in [
        "title",
        "category",
        "description",
        "version",
        "documentation-url",
        "license",
        "contributor",
        "acknowledgements",
    ]:
        el = dom.getElementsByTagName(desc_str)
        if el and el[0].firstChild and el[0].firstChild.nodeValue.strip():
            class_string += (
                desc_str + ": " + el[0].firstChild.nodeValue.strip() + "\n\n"
            )
        if desc_str == "category":
            category = el[0].firstChild.nodeValue.strip()
    class_string += '"""'

    for paramGroup in dom.getElementsByTagName("parameters"):
        indices = paramGroup.getElementsByTagName("index")
        max_index = 0
        for index in indices:
            if int(index.firstChild.nodeValue) > max_index:
                max_index = int(index.firstChild.nodeValue)
        for param in paramGroup.childNodes:
            if param.nodeName in ["label", "description", "#text", "#comment"]:
                continue
            traitsParams = {}

            longFlagNode = param.getElementsByTagName("longflag")
            if longFlagNode:
                # Prefer to use longFlag as name if it is given, rather than the parameter name
                longFlagName = longFlagNode[0].firstChild.nodeValue
                # SEM automatically strips prefixed "--" or "-" from xml before processing
                # we need to replicate that behavior here The following
                # two nodes in xml have the same behavior in the program
                # <longflag>--test</longflag>
                # <longflag>test</longflag>
                longFlagName = longFlagName.lstrip(" -").rstrip(" ")
                name = longFlagName
                name = force_to_valid_python_variable_name(name)
                traitsParams["argstr"] = "--" + longFlagName + " "
            else:
                name = param.getElementsByTagName("name")[0].firstChild.nodeValue
                name = force_to_valid_python_variable_name(name)
                if param.getElementsByTagName("index"):
                    traitsParams["argstr"] = ""
                else:
                    traitsParams["argstr"] = "--" + name + " "

            if (
                param.getElementsByTagName("description")
                and param.getElementsByTagName("description")[0].firstChild
            ):
                traitsParams["desc"] = (
                    param.getElementsByTagName("description")[0]
                    .firstChild.nodeValue.replace('"', '\\"')
                    .replace("\n", ", ")
                )

            argsDict = {
                "directory": "%s",
                "file": "%s",
                "integer": "%d",
                "double": "%f",
                "float": "%f",
                "image": "%s",
                "transform": "%s",
                "boolean": "",
                "string-enumeration": "%s",
                "string": "%s",
                "integer-enumeration": "%s",
                "table": "%s",
                "point": "%s",
                "region": "%s",
                "geometry": "%s",
            }

            if param.nodeName.endswith("-vector"):
                traitsParams["argstr"] += "%s"
            else:
                traitsParams["argstr"] += argsDict[param.nodeName]

            index = param.getElementsByTagName("index")
            if index:
                traitsParams["position"] = int(index[0].firstChild.nodeValue) - (
                    max_index + 1
                )

            desc = param.getElementsByTagName("description")
            if index:
                traitsParams["desc"] = desc[0].firstChild.nodeValue

            typesDict = {
                "integer": "traits.Int",
                "double": "traits.Float",
                "float": "traits.Float",
                "image": "File",
                "transform": "File",
                "boolean": "traits.Bool",
                "string": "traits.Str",
                "file": "File",
                "geometry": "File",
                "directory": "Directory",
                "table": "File",
                "point": "traits.List",
                "region": "traits.List",
            }

            if param.nodeName.endswith("-enumeration"):
                type = "traits.Enum"
                values = [
                    '"%s"' % str(el.firstChild.nodeValue).replace('"', "")
                    for el in param.getElementsByTagName("element")
                ]
            elif param.nodeName.endswith("-vector"):
                type = "InputMultiPath"
                if param.nodeName in [
                    "file",
                    "directory",
                    "image",
                    "geometry",
                    "transform",
                    "table",
                ]:
                    values = [
                        "%s(exists=True)"
                        % typesDict[param.nodeName.replace("-vector", "")]
                    ]
                else:
                    values = [typesDict[param.nodeName.replace("-vector", "")]]
                if mipav_hacks is True:
                    traitsParams["sep"] = ";"
                else:
                    traitsParams["sep"] = ","
            elif param.getAttribute("multiple") == "true":
                type = "InputMultiPath"
                if param.nodeName in [
                    "file",
                    "directory",
                    "image",
                    "geometry",
                    "transform",
                    "table",
                ]:
                    values = ["%s(exists=True)" % typesDict[param.nodeName]]
                elif param.nodeName in ["point", "region"]:
                    values = [
                        "%s(traits.Float(), minlen=3, maxlen=3)"
                        % typesDict[param.nodeName]
                    ]
                else:
                    values = [typesDict[param.nodeName]]
                traitsParams["argstr"] += "..."
            else:
                values = []
                type = typesDict[param.nodeName]

            if param.nodeName in [
                "file",
                "directory",
                "image",
                "geometry",
                "transform",
                "table",
            ]:
                if not param.getElementsByTagName("channel"):
                    raise RuntimeError(
                        "Insufficient XML specification: each element of type 'file', 'directory', 'image', 'geometry', 'transform',  or 'table' requires 'channel' field.\n{}".format(
                            traitsParams
                        )
                    )
                elif (
                    param.getElementsByTagName("channel")[0].firstChild.nodeValue
                    == "output"
                ):
                    traitsParams["hash_files"] = False
                    inputTraits.append(
                        "%s = traits.Either(traits.Bool, %s(%s), %s)"
                        % (
                            name,
                            type,
                            parse_values(values).replace("exists=True", ""),
                            parse_params(traitsParams),
                        )
                    )
                    traitsParams["exists"] = True
                    traitsParams.pop("argstr")
                    traitsParams.pop("hash_files")
                    outputTraits.append(
                        "%s = %s(%s%s)"
                        % (
                            name,
                            type.replace("Input", "Output"),
                            parse_values(values),
                            parse_params(traitsParams),
                        )
                    )

                    outputs_filenames[name] = gen_filename_from_param(param, name)
                elif (
                    param.getElementsByTagName("channel")[0].firstChild.nodeValue
                    == "input"
                ):
                    if param.nodeName in [
                        "file",
                        "directory",
                        "image",
                        "geometry",
                        "transform",
                        "table",
                    ] and type not in ["InputMultiPath", "traits.List"]:
                        traitsParams["exists"] = True
                    inputTraits.append(
                        "%s = %s(%s%s)"
                        % (name, type, parse_values(values), parse_params(traitsParams))
                    )
                else:
                    raise RuntimeError(
                        "Insufficient XML specification: each element of type 'file', 'directory', 'image', 'geometry', 'transform',  or 'table' requires 'channel' field to be in ['input','output'].\n{}".format(
                            traitsParams
                        )
                    )
            else:  # For all other parameter types, they are implicitly only input types
                inputTraits.append(
                    "%s = %s(%s%s)"
                    % (name, type, parse_values(values), parse_params(traitsParams))
                )

    if mipav_hacks:
        blacklisted_inputs = ["maxMemoryUsage"]
        inputTraits = [
            trait for trait in inputTraits if trait.split()[0] not in blacklisted_inputs
        ]

        compulsory_inputs = [
            'xDefaultMem = traits.Int(desc="Set default maximum heap size", argstr="-xDefaultMem %d")',
            'xMaxProcess = traits.Int(1, desc="Set default maximum number of processes.", argstr="-xMaxProcess %d", usedefault=True)',
        ]
        inputTraits += compulsory_inputs

    input_spec_code = "class " + module_name + "InputSpec(CommandLineInputSpec):\n"
    for trait in inputTraits:
        input_spec_code += "    " + trait + "\n"

    output_spec_code = "class " + module_name + "OutputSpec(TraitedSpec):\n"
    if not outputTraits:
        output_spec_code += "    pass\n"
    else:
        for trait in outputTraits:
            output_spec_code += "    " + trait + "\n"

    output_filenames_code = "_outputs_filenames = {"
    output_filenames_code += ",".join(
        [f"'{key}':'{value}'" for key, value in outputs_filenames.items()]
    )
    output_filenames_code += "}"

    input_spec_code += "\n\n"
    output_spec_code += "\n\n"

    template = """class %module_name%(SEMLikeCommandLine):
    %class_str%

    input_spec = %module_name%InputSpec
    output_spec = %module_name%OutputSpec
    _cmd = "%launcher% %name% "
    %output_filenames_code%\n"""
    template += f"    _redirect_x = {redirect_x}\n"

    main_class = (
        template.replace("%class_str%", class_string)
        .replace("%module_name%", module_name)
        .replace("%name%", module)
        .replace("%output_filenames_code%", output_filenames_code)
        .replace("%launcher%", " ".join(launcher))
    )

    return category, input_spec_code + output_spec_code + main_class, module_name


def grab_xml(module, launcher, mipav_hacks=False):
    #        cmd = CommandLine(command = "Slicer3", args="--launch %s --xml"%module)
    #        ret = cmd.run()
    command_list = launcher[:]  # force copy to preserve original
    command_list.extend([module, "--xml"])
    final_command = " ".join(command_list)
    xmlReturnValue = subprocess.Popen(
        final_command, stdout=subprocess.PIPE, shell=True
    ).communicate()[0]
    if mipav_hacks:
        # workaround for a jist bug https://www.nitrc.org/tracker/index.php?func=detail&aid=7234&group_id=228&atid=942
        new_xml = ""
        replace_closing_tag = False
        for line in xmlReturnValue.splitlines():
            if line.strip() == "<file collection: semi-colon delimited list>":
                new_xml += "<file-vector>\n"
                replace_closing_tag = True
            elif replace_closing_tag and line.strip() == "</file>":
                new_xml += "</file-vector>\n"
                replace_closing_tag = False
            else:
                new_xml += line + "\n"

        xmlReturnValue = new_xml

        # workaround for a JIST bug https://www.nitrc.org/tracker/index.php?func=detail&aid=7233&group_id=228&atid=942
        if xmlReturnValue.strip().endswith("XML"):
            xmlReturnValue = xmlReturnValue.strip()[:-3]
        if xmlReturnValue.strip().startswith("Error: Unable to set default atlas"):
            xmlReturnValue = xmlReturnValue.strip()[
                len("Error: Unable to set default atlas") :
            ]
    try:
        dom = xml.dom.minidom.parseString(xmlReturnValue.strip())
    except Exception as e:
        print(xmlReturnValue.strip())
        raise e
    return dom


#        if ret.runtime.returncode == 0:
#            return xml.dom.minidom.parseString(ret.runtime.stdout)
#        else:
#            raise Exception(cmd.cmdline + " failed:\n%s"%ret.runtime.stderr)


def parse_params(params):
    list = []
    for key, value in params.items():
        if isinstance(value, (str, bytes)):
            list.append('{}="{}"'.format(key, value.replace('"', "'")))
        else:
            list.append(f"{key}={value}")

    return ", ".join(list)


def parse_values(values):
    values = ["%s" % value for value in values]
    if len(values) > 0:
        retstr = ", ".join(values) + ", "
    else:
        retstr = ""
    return retstr


def gen_filename_from_param(param, base):
    fileExtensions = param.getAttribute("fileExtensions")
    if fileExtensions:
        # It is possible that multiple file extensions can be specified in a
        # comma separated list,  This will extract just the first extension
        firstFileExtension = fileExtensions.split(",")[0]
        ext = firstFileExtension
    else:
        ext = {
            "image": ".nii",
            "transform": ".mat",
            "file": "",
            "directory": "",
            "geometry": ".vtk",
        }[param.nodeName]
    return base + ext


if __name__ == "__main__":
    # NOTE:  For now either the launcher needs to be found on the default path, or
    # every tool in the modules list must be found on the default path
    # AND calling the module with --xml must be supported and compliant.
    modules_list = [
        "MedianImageFilter",
        "CheckerBoardFilter",
        "EMSegmentCommandLine",
        "GrayscaleFillHoleImageFilter",
        # 'CreateDICOMSeries', #missing channel
        "TractographyLabelMapSeeding",
        "IntensityDifferenceMetric",
        "DWIToDTIEstimation",
        "MaskScalarVolume",
        "ImageLabelCombine",
        "DTIimport",
        "OtsuThresholdImageFilter",
        "ExpertAutomatedRegistration",
        "ThresholdScalarVolume",
        "DWIUnbiasedNonLocalMeansFilter",
        "BRAINSFit",
        "MergeModels",
        "ResampleDTIVolume",
        "MultiplyScalarVolumes",
        "LabelMapSmoothing",
        "RigidRegistration",
        "VotingBinaryHoleFillingImageFilter",
        "BRAINSROIAuto",
        "RobustStatisticsSegmenter",
        "GradientAnisotropicDiffusion",
        "ProbeVolumeWithModel",
        "ModelMaker",
        "ExtractSkeleton",
        "GrayscaleGrindPeakImageFilter",
        "N4ITKBiasFieldCorrection",
        "BRAINSResample",
        "DTIexport",
        "VBRAINSDemonWarp",
        "ResampleScalarVectorDWIVolume",
        "ResampleScalarVolume",
        "OtsuThresholdSegmentation",
        # 'ExecutionModelTour',
        "HistogramMatching",
        "BRAINSDemonWarp",
        "ModelToLabelMap",
        "GaussianBlurImageFilter",
        "DiffusionWeightedVolumeMasking",
        "GrayscaleModelMaker",
        "CastScalarVolume",
        "DicomToNrrdConverter",
        "AffineRegistration",
        "AddScalarVolumes",
        "LinearRegistration",
        "SimpleRegionGrowingSegmentation",
        "DWIJointRicianLMMSEFilter",
        "MultiResolutionAffineRegistration",
        "SubtractScalarVolumes",
        "DWIRicianLMMSEFilter",
        "OrientScalarVolume",
        "FiducialRegistration",
        "BSplineDeformableRegistration",
        "CurvatureAnisotropicDiffusion",
        "PETStandardUptakeValueComputation",
        "DiffusionTensorScalarMeasurements",
        "ACPCTransform",
        "EMSegmentTransformToNewFormat",
        "BSplineToDeformationField",
    ]

    # SlicerExecutionModel compliant tools that are usually statically built, and don't need the Slicer3 --launcher
    generate_all_classes(modules_list=modules_list, launcher=[])
    # Tools compliant with SlicerExecutionModel called from the Slicer environment (for shared lib compatibility)
    # launcher = ['/home/raid3/gorgolewski/software/slicer/Slicer', '--launch']
    # generate_all_classes(modules_list=modules_list, launcher=launcher)
    # generate_all_classes(modules_list=['BRAINSABC'], launcher=[] )
