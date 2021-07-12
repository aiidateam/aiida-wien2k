from aiida.common import datastructures
from aiida.engine import CalcJob
from aiida.orm import SinglefileData, Dict, RemoteData, Code

def _cli_options(parameters):
    """Return command line options for parameters dictionary.

    :param dict parameters: dictionary with command line parameters
    """
    options = []
    for key, value in parameters.items():
     # Could validate: is key a known command-line option?
     if isinstance(value, bool) and value:
        options.append(f'{key}')
     elif isinstance(value, str):
        # Could validate: is value a valid regular expression?
        options.append(f'{key}')
        options.append(value)

    return options

class Wien2kInitLapw(CalcJob):
    """AiiDA calculation plugin to initialize WIEN2k calculation using init_lapw."""
    
    @classmethod
    def define(cls, spec):
        """Define inputs and outputs of the calculation."""
        # yapf: disable
        super(Wien2kInitLapw, cls).define(spec)

        # inputs/outputs
        spec.input('code', valid_type=Code, help='WIEN2k init_lapw')
        spec.input('parameters', valid_type=Dict, required=False, help='Dictionary of input arguments (if any)')
        spec.input('structfile', valid_type=SinglefileData, required=False, help='Structure file case.struct')
        spec.input('parent_folder', valid_type=RemoteData, required=False,\
                   help='parent_folder passed from a previous calulation')
        spec.inputs['metadata']['options']['resources'].default = {
                                            'num_machines': 1,
                                            'num_mpiprocs_per_machine': 1,
                                            }
        #spec.output('casefolder', valid_type=RemoteData, help='Folder where WIEN2k calculation is performed')

        spec.exit_code(300, 'ERROR_MISSING_OUTPUT_FILES',
                message='Calculation did not produce all expected output files.')
        
    
    def prepare_for_submission(self, folder):
        """
        Create input files.

        :param folder: an `aiida.common.folders.Folder` where the plugin should temporarily place all files needed by
            the calculation.
        :return: `aiida.common.datastructures.CalcInfo` instance
        """
        parameters = _cli_options(self.inputs.parameters.get_dict()) # command line args for init_lapw
        codeinfo = datastructures.CodeInfo()
        codeinfo.cmdline_params = ['-b'] + parameters # x exec [parameters]
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.stdout_name = 'init_lapw.log'
        
        remote_copy_list = []
        if 'parent_folder' in self.inputs:
            path_from = os.path.join(self.inputs.parent_folder.get_remote_path(),'case')
            remote_copy_list = [(
                self.inputs.parent_folder.computer.uuid,
                path_from, './'
            )]
        else:
            folder.get_subfolder('case', create=True) # create case subfolder

        # Prepare a `CalcInfo` to be returned to the engine
        calcinfo = datastructures.CalcInfo()
        calcinfo.codes_info = [codeinfo]
        if 'structfile' in self.inputs:
            calcinfo.local_copy_list = [
                (self.inputs.structfile.uuid, self.inputs.structfile.filename, 'case/case.struct')
            ] # copy case.struct to the local folder as new.struct
        else:
            calcinfo.local_copy_list = []
        calcinfo.remote_copy_list = remote_copy_list
        calcinfo.retrieve_list = [('case/case.in*')]

        return calcinfo