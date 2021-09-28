from aiida.engine import submit
from aiida import orm
from aiida_wien2k.workflows.eos_workchain import Wien2kEosWorkChain
import time
import numpy as np
from aiida.plugins.factories import WorkflowFactory
from aiida.orm import QueryBuilder
from aiida.schedulers.datastructures import NodeNumberJobResource

def nat_vol(structure_aiida):
    "AiiDA structure number of atoms and volume"
    structure_ase = structure_aiida.get_ase() # AiiDA -> ASE struct
    vol = structure_ase.cell.volume # cell volume
    nat = structure_ase.cell.itemsize # number of atoms
    return nat, vol

def rescale(aiida_struct, vol_target):
    """Takes AiiDA DataStructure object in and returns it scaled to a desired target volume"""
    nat, vol_in = nat_vol(aiida_struct) # AiiDA input structure number of atoms and volume
    linscale = (vol_target/vol_in)**(1./3.)
    # rescale lattice parameters
    ase = aiida_struct.get_ase()
    ase.set_cell(ase.get_cell() * float(linscale), scale_atoms=True)
    aiida_struct_out = orm.StructureData(ase=ase)
    # copy extras
    extras_dic = aiida_struct.extras
    for key,value in extras_dic.items():
        aiida_struct_out.extras[key] = value

    return aiida_struct_out


def count_running_wchains():
    """
    Count number of running workchains with a given entry point

    Return:
    count (int) - number of workchains still running (status=waiting,created) 
    """
    workchain_entry_point = 'wien2k.eos_wf'
    Wien2kScfWorkChain = WorkflowFactory(workchain_entry_point)
    query = QueryBuilder()
    query.append(Wien2kScfWorkChain) # serach workflows that match workchain_entry_point
    query.all()
    count = 0
    for node in query.iterall():
        if((node[0].process_state.value == 'waiting') or\
                (node[0].process_state.value == 'created')):
            count = count + 1 # count all waiting processes

    return count # int

def wait_to_limit_nproc(nprocmax, timeinterval):
    """
    Check number of workchains running and compare to 'nprocmax'
    If the number of greater than 'nprocmax', wait 'timeinterval' sec 
    and check again. Othervise - return
    """
    time.sleep(15) # Delay for 15 second
    while( count_running_wchains()>=nprocmax ):
        time.sleep(timeinterval) # Delay for X seconds

    return

# Setting up crystal structure(s)

elements = [
        'H'
]
# elements_all = ['H', \
#         'He', 'Li', 'Be', 'B', 'C', 'N', 'O', 'F', 'Ne', \
#         'Na', 'Mg', 'Al', 'Si', 'P', 'S', 'Cl', 'Ar', \
#         'K', 'Ca', 'Sc', 'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn', 'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr', \
#         'Rb', 'Sr', 'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd', 'In', 'Sn', 'Sb', 'Te', 'I', 'Xe', \
#         'Cs', 'Ba', 'La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd', 'Tb', 'Dy', 'Ho', 'Er', 'Tm', 'Yb', 'Lu', 'Hf', \
#             'Ta', 'W', 'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg', 'Tl', 'Pb', 'Bi', 'Po', 'At', 'Rn', \
#         'Fr', 'Ra', 'Ac', 'Th', 'Pa', 'U', 'Np', 'Pu', 'Am', 'Cm', 'Bk', 'Cf', 'Es', 'Fm', 'Md', 'No', 'Lr', 'Rf', \
#             'Db', 'Sg', 'Bh', 'Hs', 'Mt', 'Ds', 'Rg', 'Cn', 'Nh', 'Fl', 'Mc', 'Lv', 'Ts', 'Og']
#elements = elements_all[0:36] # H ... Kr
#elements = elements_all[36:65] # Rb ... Tb
#elements = elements_all[65: ] # Dy ... Og
# elements = elements_all
scale_volumes = {'H-XO3': 20} # contains volume of selected structures to rescale
configurations = ['X2O', 'XO', 'X2O3', 'X2O5', 'XO2', 'XO3']
chemformulas_compleated = []
nprocmax = 8
res = NodeNumberJobResource(num_machines=1, num_mpiprocs_per_machine=1, num_cores_per_mpiproc=1) # set resources
for node in Group.get(label='commonwf-oxides/set1/structures').nodes:
    aiida_structure = node # get structure of SiO2
    element = aiida_structure.extras['element'] # chemical element X
    configuration = aiida_structure.extras['configuration'] # X2O, XO2, etc.
    formula = element + '-' + configuration # H-XO3
    if ( (element in elements) and (configuration in configurations) ):
        print(node.extras) # info about chem. composition
        chemformula = aiida_structure.get_formula()
        if (chemformula in chemformulas_compleated):
            continue # skip iteration
        if scale_volumes:
            # loop through formula-volumes dict to find relevant structure (if present)
            for key,vol_target in scale_volumes.items(): 
                if( key == formula ):
                    aiida_structure = rescale(aiida_structure,vol_target)
                    continue # exit loop of formula-volumes
        # run EOS workchain
        code1 = orm.load_code(label='wien2k-x-sgroup@localhost')
        code2 = orm.load_code(label='wien2k-init_lapw@localhost')
        code3 = orm.load_code(label='wien2k-run_lapw@localhost')
        code4 = orm.load_code(label='wien2k-x-optimize@localhost')
        code5 = orm.load_code(label='wien2k-run_lapw_clmextrapol@localhost')
        inpdict1 = orm.Dict(dict={}) # x sgroup [param]
        #inpdict2 = orm.Dict(dict={'-red':'3', '-prec':'2', '-hdlo':True, '-fermit':'0.002'}) # init_lapw -b [param]
        inpdict2 = orm.Dict(dict={'-red':'3', '-prec':'2', '-hdlo':True}) # init_lapw -b [param]
        inpdict3 = orm.Dict(dict={'-i':'100', '-ec':'0.000001', '-cc':'0.0001'}) # run_lapw [param]
        inparr4 = orm.ArrayData()
        inparr4.set_array('dvolumes', np.array([-6,-4,-2,2,4,6])) # volme change in % (exclude 0)
        result = submit(Wien2kEosWorkChain, aiida_structure=aiida_structure,\
                code1=code1, code2=code2, code3=code3, code4=code4, code5=code5,\
                inpdict1=inpdict1, inpdict2=inpdict2, inpdict3=inpdict3, inparr4=inparr4)
        print('result=', result)
        wait_to_limit_nproc(nprocmax, timeinterval=30) # limit number of concurent processes
