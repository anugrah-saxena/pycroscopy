# -*- coding: utf-8 -*-
"""
Created on Thu Aug 25 11:48:53 2016

@author: Suhas Somnath, Chris R. Smith, Rama K. Vasudevan

"""

from __future__ import division, print_function, absolute_import, unicode_literals

from warnings import warn

import numpy as np
import scipy
from sklearn.cluster import KMeans
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import pdist
from .model import Model
from .utils.be_loop import projectLoop, fit_loop, generate_guess, calc_switching_coef_vec, switching32
from .utils.tree import ClusterTree
from .be_sho_model import sho32
from .fit_methods import BE_Fit_Methods
from .optimize import Optimize
from ..io.io_utils import realToCompound, compound_to_scalar
from ..io.hdf_utils import getH5DsetRefs, getAuxData, copyRegionRefs, linkRefs, linkRefAsAlias, \
    get_sort_order, get_dimensionality, reshape_to_Ndims, reshape_from_Ndims, create_empty_dataset, buildReducedSpec, \
    get_attr
from ..io.microdata import MicroDataset, MicroDataGroup

'''
Custom dtypes for the datasets created during fitting.
'''
# loop_metrics32 = np.dtype([('Area', np.float32),
#                            ('Centroid x', np.float32),
#                            ('Centroid y', np.float32),
#                            ('Rotation Angle [rad]', np.float32),
#                            ('Offset', np.float32)])
loop_metrics32 = np.dtype({'names': ['Area', 'Centroid x', 'Centroid y', 'Rotation Angle [rad]', 'Offset'],
                           'formats': [np.float32, np.float32, np.float32, np.float32, np.float32]})

# crit32 = np.dtype([('AIC_loop', np.float32),
#                    ('BIC_loop', np.float32),
#                    ('AIC_line', np.float32),
#                    ('BIC_line', np.float32)])
crit32 = np.dtype({'names': ['AIC_loop', 'BIC_loop', 'AIC_line', 'BIC_line'],
                   'formats': [np.float32, np.float32, np.float32, np.float32]})

# loop_fit32 = np.dtype([('a_0', np.float32),
#                        ('a_1', np.float32),
#                        ('a_2', np.float32),
#                        ('a_3', np.float32),
#                        ('a_4', np.float32),
#                        ('b_0', np.float32),
#                        ('b_1', np.float32),
#                        ('b_2', np.float32),
#                        ('b_3', np.float32),
#                        ('R2 Criterion', np.float32)])
field_names = ['a_0', 'a_1', 'a_2', 'a_3', 'a_4', 'b_0', 'b_1', 'b_2', 'b_3', 'R2 Criterion']
loop_fit32 = np.dtype({'names': field_names,
                       'formats': [np.float32 for name in field_names]})

class BELoopModel(Model):
    """
    Analysis of Band excitation loops using functional fits
    
    Parameters
    ----------
    h5_main : h5py.Dataset instance
        The dataset over which the analysis will be performed. This dataset should be linked to the spectroscopic
        indices and values, and position indices and values datasets.
    variables : list(string), Default ['Frequency']
        Lists of attributes that h5_main should possess so that it may be analyzed by Model.
    parallel : bool, optional
        Should the parallel implementation of the fitting be used.  Default True.

    Returns
    -------
    None
    
    """

    def __init__(self, h5_main, variables=['DC_Offset'], parallel=True):
        super(BELoopModel, self).__init__(h5_main, variables, parallel)
        self._h5_group = None
        self.h5_guess_parameters = None
        self.h5_fit_parameters = None
        self._sho_spec_inds = None
        self._sho_spec_vals = None  # used only at one location. can remove if deemed unnecessary
        self._met_spec_inds = None
        self._num_forcs = 1
        self._num_forc_repeats = 1
        self._sho_pos_inds = None
        self._current_pos_slice = slice(None)
        self._current_sho_spec_slice = slice(None)
        self._current_met_spec_slice = slice(None)
        self._dc_offset_index = 0
        self._sho_all_but_forc_inds = None
        self._sho_all_but_dc_forc_inds = None
        self._met_all_but_forc_inds = None
        self._current_forc = 0

    def _is_legal(self, h5_main, variables=['DC_Offset']):
        """
        Checks whether or not the provided object can be analyzed by this class.

        Parameters
        ----------
        h5_main : h5py.Dataset instance
            The dataset containing the SHO Fit (not necessarily the dataset directly resulting from SHO fit)
            over which the loop projection, guess, and fit will be performed.
        variables : list(string)
            The dimensions needed to be present in the attributes of h5_main to analyze the data with Model.

        Returns
        -------
        legal : Boolean
            Whether or not this dataset satisfies the necessary conditions for analysis

        """
        if get_attr(h5_main.file, 'data_type') != 'BEPSData':
            warn('Provided dataset does not appear to be a BEPS dataset')
            return False
        elif not h5_main.name.startswith('/Measurement_'):
            warn('Provided dataset is not derived from a measurement group')
            return False

        meas_grp_name = h5_main.name.split('/')
        h5_meas_grp = h5_main.file[meas_grp_name[1]]

        if get_attr(h5_meas_grp, 'VS_mode') not in ['DC modulation mode', 'current mode']:
            warn('Provided dataset is not a DC modulation or current mode BEPS dataset')
            return False
        elif get_attr(h5_meas_grp, 'VS_cycle_fraction') != 'full':
            warn('Provided dataset does not have full cycles')
            return False
        elif h5_main.dtype != sho32:
            warn('Provided dataset is not a SHO results dataset.')
            return False

        return super(BELoopModel, self)._is_legal(h5_main, variables)

    def _set_guess(self, h5_guess):
        """
        Setup to run the fit on an existing guess dataset.  Sets the attributes
        normally defined during do_guess.

        Parameters
        ----------
        h5_guess : h5py.Dataset
            Dataset object containing the guesses

        """
        '''
        Get the Spectroscopic and Position datasets from `self.h5_main`
        '''
        self._sho_spec_inds = getAuxData(self.h5_main, auxDataName=['Spectroscopic_Indices'])[0]
        self._sho_spec_vals = getAuxData(self.h5_main, auxDataName=['Spectroscopic_Values'])[0]
        self._sho_pos_inds = getAuxData(self.h5_main, auxDataName=['Position_Indices'])[0]

        '''
        Find the Spectroscopic index for the DC_Offset
        '''
        dc_ind = np.argwhere(get_attr(self._sho_spec_vals, 'labels') == 'DC_Offset').squeeze()
        self._dc_spec_index = dc_ind
        self._dc_offset_index = 1 + dc_ind

        '''
        Get the group and projection datasets
        '''
        self._h5_group = h5_guess.parent
        self.h5_projected_loops = self._h5_group['Projected_Loops']
        self.h5_loop_metrics = self._h5_group['Loop_Metrics']
        self._met_spec_inds = self._h5_group['Loop_Metrics_Indices']

        self.h5_guess = h5_guess

    def do_guess(self, max_mem=None, processors=None, get_loop_parameters=True, verbose=False):
        """
        Compute the loop projections and the initial guess for the loop parameters.
        
        Parameters
        ----------
        processors : uint, optional
            Number of processors to use for computing. Currently this is a serial operation and this attribute is
            ignored.
            Default None, output of psutil.cpu_count - 2 is used
        max_mem : uint, optional
            Memory in MB to use for computation
            Default None, available memory from psutil.virtual_memory is used
        get_loop_parameters : bool, optional
            Should the physical loop parameters be calculated after the guess is done
            Default True
        verbose : bool, optional
            Whether or not to print debug statements
            Default False

        Returns
        -------
        h5_guess : h5py.Dataset object
            h5py dataset containing the guess parameters
        """

        # Before doing the Guess, we must first project the loops
        self._create_projection_datasets()
        if max_mem is None:
            max_mem = self._maxDataChunk
        else:
            max_mem = min(max_mem, self._maxMemoryMB)
            self._maxDataChunk = int(max_mem / self._maxCpus)

        self._get_sho_chunk_sizes(max_mem, verbose=verbose)
        self._create_guess_datasets()

        '''
        Get the first slice of the sho and loop metrics
        '''
        self._current_sho_spec_slice = slice(self.sho_spec_inds_per_forc * self._current_forc,
                                             self.sho_spec_inds_per_forc * (self._current_forc + 1))
        self._current_met_spec_slice = slice(self.metrics_spec_inds_per_forc * self._current_forc,
                                             self.metrics_spec_inds_per_forc * (self._current_forc + 1))

        '''
        Get the dc_offset and data_chunk for the first slice
        '''
        self._get_dc_offset(verbose=verbose)
        self._get_data_chunk(verbose=verbose)

        '''
        Loop over positions
        '''
        while self.data is not None:
            # Reshape the SHO
            print('Generating Guesses for FORC {}, and positions {}-{}'.format(self._current_forc,
                                                                               self._start_pos,
                                                                               self._end_pos))
            '''
            Reshape the sho data by loops
            '''
            if len(self._sho_all_but_forc_inds) == 1:
                # Check for the special case where there is only one loop
                loops_2d = np.transpose(self.data)
                order_dc_offset_reverse = np.array([1, 0], dtype=np.uint8)
                nd_mat_shape_dc_first = loops_2d.shape
            else:
                loops_2d, order_dc_offset_reverse, nd_mat_shape_dc_first = self._reshape_sho_matrix(self.data,
                                                                                                    verbose=verbose)

            '''
            Do the projection and guess
            '''
            projected_loops_2d, loop_metrics_1d = self._project_loop_batch(self.dc_vec, np.transpose(loops_2d))
            guessed_loops = self._guess_loops(self.dc_vec, projected_loops_2d)

            # Reshape back
            if len(self._sho_all_but_forc_inds) != 1:
                projected_loops_2d = self._reshape_projected_loops_for_h5(projected_loops_2d.T,
                                                                          order_dc_offset_reverse,
                                                                          nd_mat_shape_dc_first,
                                                                          verbose=verbose)

            metrics_2d = self._reshape_results_for_h5(loop_metrics_1d, nd_mat_shape_dc_first, verbose=verbose)
            guessed_loops_2 = self._reshape_results_for_h5(guessed_loops, nd_mat_shape_dc_first, verbose=verbose)

            # Store results
            self.h5_projected_loops[self._start_pos:self._end_pos, self._current_sho_spec_slice] = projected_loops_2d
            self.h5_loop_metrics[self._start_pos:self._end_pos, self._current_met_spec_slice] = metrics_2d
            self.h5_guess[self._start_pos:self._end_pos, self._current_met_spec_slice] = guessed_loops_2

            '''
            Change the starting position and get the next chunk of data
            '''
            self._start_pos = self._end_pos
            self._get_data_chunk(verbose=verbose)

        if get_loop_parameters:
            self.h5_guess_parameters = self.extract_loop_parameters(self.h5_guess)

        return self.h5_guess

    def do_fit(self, processors=None, max_mem=None, solver_type='least_squares', solver_options={'jac': '2-point'},
               obj_func={'class': 'BE_Fit_Methods', 'obj_func': 'BE_LOOP', 'xvals': np.array([])},
               get_loop_parameters=True, h5_guess=None, verbose=False):
        """
        Fit the loops

        Parameters
        ----------
        processors : uint, optional
            Number of processors to use for computing. Currently this is a serial operation
            Default None, output of psutil.cpu_count - 2 is used
        max_mem : uint, optional
            Memory in MB to use for computation
            Default None, available memory from psutil.virtual_memory is used
        solver_type : str
            Which solver from scipy.optimize should be used to fit the loops
        solver_options : dict of str
            Parameters to be passed to the solver defined by `solver_type`
        obj_func : dict of str
            Dictionary defining the class and method for the loop residual function as well
            as the parameters to be passed
        get_loop_parameters : bool, optional
            Should the physical loop parameters be calculated after the guess is done
            Default True
        h5_guess : h5py.Dataset
            Existing guess to use as input to fit.
            Default None
        verbose : Boolean
            Whether or not to print debugging statements

        Returns
        -------
        results: list
            List of the results returned by the solver

        """
        '''
        Set the number of processors and the ammount of RAM to use in the fit
        '''
        if processors is None:
            processors = self._maxCpus
        else:
            processors = min(processors, self._maxCpus)
        if max_mem is None:
            max_mem = self._maxDataChunk
        else:
            max_mem = min(max_mem, self._maxMemoryMB)
            self._maxDataChunk = int(max_mem / self._maxCpus)

        '''
        Ensure that a guess exists
        '''
        if h5_guess is not None:
            self._set_guess(h5_guess)
        elif self.h5_guess is None:
            print("You need to guess before fitting\n")
            return None

        '''
        Setup the datasets
        '''
        self._create_fit_dataset()
        self._get_sho_chunk_sizes(max_mem, verbose=verbose)

        '''
        Get the dc_vector and the data for the first loop
        '''
        self._start_pos = 0
        self._current_forc = 0
        self._current_sho_spec_slice = slice(self.sho_spec_inds_per_forc * self._current_forc,
                                             self.sho_spec_inds_per_forc * (self._current_forc + 1))
        self._current_met_spec_slice = slice(self.metrics_spec_inds_per_forc * self._current_forc,
                                             self.metrics_spec_inds_per_forc * (self._current_forc + 1))
        self._get_dc_offset(verbose=verbose)
        self._get_guess_chunk()

        '''
        Reshape the sho data by loop
        '''
        if len(self._sho_all_but_forc_inds) == 1:
            # Check for the special case of a single loop
            loops_2d = np.transpose(self.data)
            nd_mat_shape_dc_first = loops_2d.shape
        else:
            loops_2d, _, nd_mat_shape_dc_first = self._reshape_sho_matrix(self.data,
                                                                          verbose=verbose)

        '''
        Shift the loops and vdc vector
        '''
        shift_ind, vdc_shifted = self.shift_vdc(self.dc_vec)
        loops_2d_shifted = np.roll(loops_2d, shift_ind, axis=0).T

        '''
        Do the fit
        '''
        results = list()
        legit_solver = solver_type in scipy.optimize.__dict__.keys()
        legit_obj_func = obj_func['obj_func'] in BE_Fit_Methods().methods
        if legit_solver and legit_obj_func:
            print("Using solver {} and objective function {} to fit your data\n".format(solver_type,
                                                                                        obj_func['obj_func']))
            while self.data is not None:
                opt = LoopOptimize(data=loops_2d_shifted, guess=self.guess, parallel=self._parallel)
                temp = opt.computeFit(processors=processors, solver_type=solver_type, solver_options=solver_options,
                                      obj_func={'class': 'BE_Fit_Methods', 'obj_func': 'BE_LOOP', 'xvals': vdc_shifted})
                # TODO: need a different .reformatResults to process fitting results
                temp = self._reformat_results(temp, obj_func['obj_func'])
                temp = self._reshape_results_for_h5(temp, nd_mat_shape_dc_first, verbose=verbose)

                results.append(temp)

                self._start_pos = self._end_pos
                self._get_guess_chunk(verbose=verbose)

            self.fit = np.hstack(tuple(results))
            self._set_results()

        elif legit_obj_func:
            warn('Error: Solver "%s" does not exist!. For additional info see scipy.optimize\n' % solver_type)
            return None
        elif legit_solver:
            warn('Error: Objective Functions "%s" is not implemented in pycroscopy.analysis.Fit_Methods' %
                 (obj_func['obj_func']))
            return None

        if get_loop_parameters:
            self.h5_fit_parameters = self.extract_loop_parameters(self.h5_fit)

        return self.h5_fit

    @staticmethod
    def extract_loop_parameters(h5_loop_fit, nuc_threshold=0.03):
        """
        Method to extract a set of physical loop parameters from a dataset of fit parameters

        Parameters
        ----------
        h5_loop_fit : h5py.Dataset
            Dataset of loop fit parameters
        nuc_threshold : float
            Nucleation threshold to use in calculation physical parameters

        Returns
        -------
        h5_loop_parm : h5py.Dataset
            Dataset of physical parameters
        """
        dset_name = h5_loop_fit.name+'_Loop_Parameters'
        h5_loop_parameters = create_empty_dataset(h5_loop_fit, dtype=switching32,
                                                  dset_name=dset_name,
                                                  new_attrs={'nuc_threshold': nuc_threshold})

        loop_coef_vec = compound_to_scalar(np.reshape(h5_loop_fit, [-1, 1]))
        switching_coef_vec = calc_switching_coef_vec(loop_coef_vec, nuc_threshold)

        h5_loop_parameters[:, :] = switching_coef_vec.reshape(h5_loop_fit.shape)

        return h5_loop_parameters

    def _create_projection_datasets(self):
        """
        Setup the Loop_Fit Group and the loop projection datasets

        """
        # First grab the spectroscopic indices and values and position indices
        self._sho_spec_inds = getAuxData(self.h5_main, auxDataName=['Spectroscopic_Indices'])[0]
        self._sho_spec_vals = getAuxData(self.h5_main, auxDataName=['Spectroscopic_Values'])[0]
        self._sho_pos_inds = getAuxData(self.h5_main, auxDataName=['Position_Indices'])[0]

        dc_ind = np.argwhere(get_attr(self._sho_spec_vals, 'labels') == 'DC_Offset').squeeze()
        not_dc = get_attr(self._sho_spec_vals, 'labels') != 'DC_Offset'

        self._dc_spec_index = dc_ind
        self._dc_offset_index = 1 + dc_ind

        # Calculate the number of loops per position
        cycle_start_inds = np.argwhere(self._sho_spec_inds[dc_ind, :] == 0).flatten()
        tot_cycles = cycle_start_inds.size

        # Prepare containers for the dataets
        ds_projected_loops = MicroDataset('Projected_Loops', data=[], dtype=np.float32,
                                          maxshape=self.h5_main.shape, chunking=self.h5_main.chunks,
                                          compression='gzip')
        ds_loop_metrics = MicroDataset('Loop_Metrics', data=[], dtype=loop_metrics32,
                                       maxshape=(self.h5_main.shape[0], tot_cycles))

        ds_loop_met_spec_inds, ds_loop_met_spec_vals = buildReducedSpec(self._sho_spec_inds, self._sho_spec_vals,
                                                                        not_dc, cycle_start_inds,
                                                                        basename='Loop_Metrics')

        # name of the dataset being projected.
        dset_name = self.h5_main.name.split('/')[-1]

        proj_grp = MicroDataGroup('-'.join([dset_name, 'Loop_Fit_']),
                                  self.h5_main.parent.name[1:])
        proj_grp.attrs['projection_method'] = 'pycroscopy BE loop model'
        proj_grp.addChildren([ds_projected_loops, ds_loop_metrics,
                              ds_loop_met_spec_inds, ds_loop_met_spec_vals])

        h5_proj_grp_refs = self.hdf.writeData(proj_grp)
        self.h5_projected_loops = getH5DsetRefs(['Projected_Loops'], h5_proj_grp_refs)[0]
        self.h5_loop_metrics = getH5DsetRefs(['Loop_Metrics'], h5_proj_grp_refs)[0]
        self._met_spec_inds = getH5DsetRefs(['Loop_Metrics_Indices'], h5_proj_grp_refs)[0]
        h5_loop_met_spec_vals = getH5DsetRefs(['Loop_Metrics_Values'], h5_proj_grp_refs)[0]
        self._h5_group = h5_loop_met_spec_vals.parent

        h5_pos_dsets = getAuxData(self.h5_main, auxDataName=['Position_Indices',
                                                             'Position_Values'])
        # do linking here
        # first the positions
        linkRefs(self.h5_projected_loops, h5_pos_dsets)
        linkRefs(self.h5_projected_loops, [self.h5_loop_metrics])
        linkRefs(self.h5_loop_metrics, h5_pos_dsets)
        # then the spectroscopic
        linkRefs(self.h5_projected_loops, [self._sho_spec_inds, self._sho_spec_vals])
        linkRefAsAlias(self.h5_loop_metrics, self._met_spec_inds, 'Spectroscopic_Indices')
        linkRefAsAlias(self.h5_loop_metrics, h5_loop_met_spec_vals, 'Spectroscopic_Values')

        copyRegionRefs(self.h5_main, self.h5_projected_loops)
        copyRegionRefs(self.h5_main, self.h5_loop_metrics)

        self.hdf.flush()

        return

    def _get_sho_chunk_sizes(self, max_mem_mb, verbose=False):
        """
        Calculates the largest number of positions that can be read into memory for a single FORC cycle

        Parameters
        ----------
        max_mem_mb : unsigned int
            Maximum allowable memory in megabytes
        verbose : Boolean (Optional. Default is False)
            Whether or not to print debugging statements

        Returns
        -------
        max_pos : unsigned int
            largest number of positions that can be read into memory for a single FORC cycle
        sho_spec_inds_per_forc : unsigned int
            Number of indices in the SHO spectroscopic table that will be used per read
        metrics_spec_inds_per_forc : unsigned int
            Number of indices in the Loop metrics spectroscopic table that will be used per read
        """
        # Step 1: Find number of FORC cycles and repeats (if any), DC steps, and number of loops
        # dc_offset_index = np.argwhere(self._sho_spec_inds.attrs['labels'] == 'DC_Offset').squeeze()
        num_dc_steps = np.unique(self._sho_spec_inds[self._dc_spec_index, :]).size
        all_spec_dims = list(range(self._sho_spec_inds.shape[0]))
        all_spec_dims.remove(self._dc_spec_index)

        # Remove FORC_cycles
        sho_spec_labels = get_attr(self._sho_spec_inds, 'labels')
        has_forcs = 'FORC' in sho_spec_labels or 'FORC_Cycle' in sho_spec_labels
        if has_forcs:
            forc_name = 'FORC' if 'FORC' in sho_spec_labels else 'FORC_Cycle'
            forc_pos = np.argwhere(sho_spec_labels == forc_name)[0][0]
            self._num_forcs = np.unique(self._sho_spec_inds[forc_pos]).size
            all_spec_dims.remove(forc_pos)

            # Remove FORC_repeats
            has_forc_repeats = 'FORC_repeat' in sho_spec_labels
            if has_forc_repeats:
                forc_repeat_pos = np.argwhere(sho_spec_labels == 'FORC_repeat')[0][0]
                self._num_forc_repeats = np.unique(self._sho_spec_inds[forc_repeat_pos]).size
                all_spec_dims.remove(forc_repeat_pos)

        # calculate number of loops:
        loop_dims = get_dimensionality(self._sho_spec_inds, all_spec_dims)
        loops_per_forc = np.product(loop_dims)

        # Step 2: Calculate the largest number of FORCS and positions that can be read given memory limits:
        size_per_forc = num_dc_steps * loops_per_forc * len(self.h5_main.dtype) * self.h5_main.dtype[0].itemsize
        """
        How we arrive at the number for the overhead (how many times the size of the data-chunk we will use in memory)
        1 for the original data, 1 for data copied to all children processes, 1 for results, 0.5 for fit, guess, misc
        """
        mem_overhead = 3.5
        max_pos = int(max_mem_mb * 1024 ** 2 / (size_per_forc * mem_overhead))
        if verbose:
            print('Can read {} of {} pixels given a {} MB memory limit'.format(max_pos,
                                                                               self._sho_pos_inds.shape[0],
                                                                               max_mem_mb))
        self.max_pos = int(min(self._sho_pos_inds.shape[0], max_pos))
        self.sho_spec_inds_per_forc = int(self._sho_spec_inds.shape[1] / self._num_forcs / self._num_forc_repeats)
        self.metrics_spec_inds_per_forc = int(self._met_spec_inds.shape[1] / self._num_forcs / self._num_forc_repeats)

        # Step 3: Read allowed chunk
        self._sho_all_but_forc_inds = list(range(self._sho_spec_inds.shape[0]))
        self._met_all_but_forc_inds = list(range(self._met_spec_inds.shape[0]))
        if self._num_forcs > 1:
            self._sho_all_but_forc_inds.remove(forc_pos)
            met_forc_pos = np.argwhere(get_attr(self._met_spec_inds, 'labels') == forc_name)[0][0]
            self._met_all_but_forc_inds.remove(met_forc_pos)

            if self._num_forc_repeats > 1:
                self._sho_all_but_forc_inds.remove(forc_repeat_pos)
                met_forc_repeat_pos = np.argwhere(get_attr(self._met_spec_inds, 'labels') == 'FORC_repeat')[0][0]
                self._met_all_but_forc_inds.remove(met_forc_repeat_pos)

        return

    def _reshape_sho_matrix(self, raw_2d, verbose=False):
        """
        Reshapes the raw 2D SHO matrix (as read from the file) to 2D array
        arranged as [instance x points for a single loop]

        Parameters
        ----------
        raw_2d : 2D compound numpy array
            Raw SHO fitted data arranged as [position, data for a single FORC cycle]
        verbose : Boolean (Optional. Default is False)
            Whether or not to print debugging statements

        Returns
        -------
        loops_2d : 2D numpy compound array
            SHO fitted data arranged as [instance or position x dc voltage steps]
        order_dc_offset_reverse : tuple
            Order in which the N dimensional data should be transposed to return it to the same format
            as the input data of this function
        nd_mat_shape_dc_first : 1D numpy unsigned int array
            Shape of the N dimensional array that the loops_2d can be turned into.
            Use the order_dc_offset_reverse after this reshape
        """
        # step 4: reshape to N dimensions
        fit_nd, success = reshape_to_Ndims(raw_2d,
                                           h5_pos=None,
                                           h5_spec=self._sho_spec_inds[self._sho_all_but_forc_inds,
                                                                       self._current_sho_spec_slice])
        dim_names_orig = np.hstack(('Positions',
                                    get_attr(self._sho_spec_inds, 'labels')[self._sho_all_but_forc_inds]))

        if not success:
            warn('Error - could not reshape provided raw data chunk...')
            return None
        if verbose:
            print('Shape of N dimensional dataset:', fit_nd.shape)
            print('Dimensions of order:', dim_names_orig)

        # order_dc_outside_nd = np.roll(range(fit_nd.ndim), -self._dc_offset_index)
        # order_dc_offset_reverse = np.roll(range(fit_nd.ndim), self._dc_offset_index)

        # step 5: Move the voltage dimension to the first dim
        order_dc_outside_nd = [self._dc_offset_index] + list(range(self._dc_offset_index)) + \
                              list(range(self._dc_offset_index + 1, len(fit_nd.shape)))
        order_dc_offset_reverse = list(range(1, self._dc_offset_index + 1)) + [0] + \
                                  list(range(self._dc_offset_index + 1, len(fit_nd.shape)))
        fit_nd2 = np.transpose(fit_nd, tuple(order_dc_outside_nd))
        dim_names_dc_out = dim_names_orig[order_dc_outside_nd]
        if verbose:
            print('originally:', fit_nd.shape, ', after moving DC offset outside:', fit_nd2.shape)
            print('new dim names:', dim_names_dc_out)

        # step 6: reshape the ND data to 2D arrays
        loops_2d = np.reshape(fit_nd2, (fit_nd2.shape[0], -1))
        if verbose:
            print('Loops ready to be projected of shape (Vdc, all other dims besides FORC):', loops_2d.shape)

        return loops_2d, order_dc_offset_reverse, fit_nd2.shape

    def _reshape_projected_loops_for_h5(self, projected_loops_2d, order_dc_offset_reverse,
                                        nd_mat_shape_dc_first, verbose=False):
        """
        Reshapes the 2D projected loops to the format such that they can be written to the h5 file

        Parameters
        ----------
        projected_loops_2d : 2D numpy float array
            Projected loops arranged as [instance or position x dc voltage steps]
        order_dc_offset_reverse : tuple of unsigned ints
            Order in which the N dimensional data should be transposed to return it to the format used in h5 files
        nd_mat_shape_dc_first : 1D numpy unsigned int array
            Shape of the N dimensional array that the loops_2d can be turned into.
            We use the order_dc_offset_reverse after this reshape
        verbose : Boolean (Optional. Default is False)
            Whether or not to print debugging statements

        Returns
        -------
        proj_loops_2d : 2D numpy float array
            Projected loops reshaped to the original chronological order in which the data was acquired
        """
        if verbose:
            print('Projected loops of shape:', projected_loops_2d.shape, ', need to bring to:', nd_mat_shape_dc_first)
        # Step 9: Reshape back to same shape as fit_Nd2:
        projected_loops_nd = np.reshape(projected_loops_2d, nd_mat_shape_dc_first)
        if verbose:
            print('Projected loops reshaped to N dimensions :', projected_loops_nd.shape)
        # Step 10: Move Vdc back inwards. Only for projected loop
        projected_loops_nd_2 = np.transpose(projected_loops_nd, order_dc_offset_reverse)
        if verbose:
            print('Projected loops after moving DC offset inwards:', projected_loops_nd_2.shape)
        # step 11: reshape back to 2D
        proj_loops_2d, success = reshape_from_Ndims(projected_loops_nd_2,
                                                    h5_pos=None,
                                                    h5_spec=self._sho_spec_inds[self._sho_all_but_forc_inds,
                                                                                self._current_sho_spec_slice])
        if not success:
            warn('unable to reshape projected loops')
            return None
        if verbose:
            print('loops shape after collapsing dimensions:', proj_loops_2d.shape)

        return proj_loops_2d

    def _reshape_results_for_h5(self, raw_results, nd_mat_shape_dc_first, verbose=False):
        """
        Reshapes the 1D loop metrics to the format such that they can be written to the h5 file

        Parameters
        ----------

        raw_results : 2D numpy float array
            loop metrics arranged as [instance or position x metrics]
        nd_mat_shape_dc_first : 1D numpy unsigned int array
            Shape of the N dimensional array that the raw_results can be turned into.
            We use the order_dc_offset_reverse after this reshape
        verbose : Boolean (Optional. Default is False)
            Whether or not to print debugging statements

        Returns
        -------
        metrics_2d : 2D numpy float array
            Loop metrics reshaped to the original chronological order in which the data was acquired
        """
        if verbose:
            print('Loop metrics of shape:', raw_results.shape)
        # Step 9: Reshape back to same shape as fit_Nd2:
        if not self._met_all_but_forc_inds:
            spec_inds = None
            loop_metrics_nd = np.reshape(raw_results, [-1, 1])
        else:
            spec_inds = self._met_spec_inds[self._met_all_but_forc_inds, self._current_met_spec_slice]
            loop_metrics_nd = np.reshape(raw_results, nd_mat_shape_dc_first[1:])

        if verbose:
            print('Loop metrics reshaped to N dimensions :', loop_metrics_nd.shape)

        # step 11: reshape back to 2D
        metrics_2d, success = reshape_from_Ndims(loop_metrics_nd,
                                                 h5_pos=None,
                                                 h5_spec=spec_inds)
        if not success:
            warn('unable to reshape ND results back to 2D')
            return None
        if verbose:
            print('metrics shape after collapsing dimensions:', metrics_2d.shape)

        return metrics_2d

    def _get_dc_offset(self, verbose=False):
        """
        Gets the DC offset for the current FORC step

        Parameters
        ----------
        verbose : boolean (optional)
            Whether or not to print debugging statements

        Returns
        -------
        dc_vec : 1D float numpy array
            DC offsets for the current FORC step
        """

        spec_sort = get_sort_order(self._sho_spec_inds[self._sho_all_but_forc_inds, self._current_sho_spec_slice])
        # get the size for each of these dimensions
        spec_dims = get_dimensionality(self._sho_spec_inds[self._sho_all_but_forc_inds,
                                                           self._current_sho_spec_slice], spec_sort)
        # apply this knowledge to reshape the spectroscopic values
        # remember to reshape such that the dimensions are arranged in reverse order (slow to fast)
        spec_vals_nd = np.reshape(self._sho_spec_vals[self._sho_all_but_forc_inds, self._current_sho_spec_slice],
                                  [-1] + spec_dims[::-1])
        # This should result in a N+1 dimensional matrix where the first index contains the actual data
        # the other dimensions are present to easily slice the data
        spec_labels_sorted = np.hstack(('Dim', get_attr(self._sho_spec_inds, 'labels')[spec_sort[::-1]]))
        if verbose:
            print('Spectroscopic dimensions sorted by rate of change:')
            print(spec_labels_sorted)
        # slice the N dimensional dataset such that we only get the DC offset for default values of other dims
        dc_pos = np.argwhere(spec_labels_sorted == 'DC_Offset')[0][0]
        dc_slice = list()
        for dim_ind in range(spec_labels_sorted.size):
            if dim_ind == dc_pos:
                dc_slice.append(slice(None))
            else:
                dc_slice.append(slice(0, 1))
        if verbose:
            print('slice to extract Vdc:')
            print(dc_slice)

        self.dc_vec = np.squeeze(spec_vals_nd[tuple(dc_slice)])

        return

    @staticmethod
    def _project_loop_batch(dc_offset, sho_mat):
        """
        This function projects loops given a matrix of the amplitude and phase.
        These matrices (and the Vdc vector) must have a single cycle's worth of
        points on the second dimension

        Parameters
        ----------
        dc_offset : 1D list or numpy array
            DC voltages. vector of length N
        sho_mat : 2D compound numpy array of type - sho32
            SHO response matrix of size MxN - [pixel, dc voltage]

        Returns
        -------
        results : tuple
            Results from projecting the provided matrices with following components

            projected_loop_mat : MxN numpy array
                Array of Projected loops
            ancillary_mat : M, compound numpy array
                This matrix contains the ancillary information extracted when projecting the loop.
                It contains the following components per loop:
                    'Area' : geometric area of the loop

                    'Centroid x': x positions of centroids for each projected loop

                    'Centroid y': y positions of centroids for each projected loop

                    'Rotation Angle': Angle by which loop was rotated [rad]

                    'Offset': Offset removed from loop
        Note
        -----
        This is the function that can be made parallel if need be.
        However, it is fast enough as is
        """
        num_pixels = int(sho_mat.shape[0])
        projected_loop_mat = np.zeros(shape=sho_mat.shape, dtype=np.float32)
        ancillary_mat = np.zeros(shape=num_pixels, dtype=loop_metrics32)

        for pixel in range(num_pixels):
            """if pixel % 50 == 0:
                print("Projecting Loop {} of {}".format(pixel, num_pixels))"""

            pix_dict = projectLoop(np.squeeze(dc_offset),
                                   sho_mat[pixel]['Amplitude [V]'],
                                   sho_mat[pixel]['Phase [rad]'])

            projected_loop_mat[pixel, :] = pix_dict['Projected Loop']
            ancillary_mat[pixel]['Rotation Angle [rad]'] = pix_dict['Rotation Matrix'][0]
            ancillary_mat[pixel]['Offset'] = pix_dict['Rotation Matrix'][1]
            ancillary_mat[pixel]['Area'] = pix_dict['Geometric Area']
            ancillary_mat[pixel]['Centroid x'] = pix_dict['Centroid'][0]
            ancillary_mat[pixel]['Centroid y'] = pix_dict['Centroid'][1]

        return projected_loop_mat, ancillary_mat

    def _project_loops(self, verbose=False):
        """
        Do the projection of the SHO fit
        Parameters
        ----------
        verbose : Boolean
            Whether or not to print debugging statements
        """

        self._create_projection_datasets()
        self._get_sho_chunk_sizes(10, verbose=verbose)

        '''
        Loop over the FORCs
        '''
        for forc_chunk_index in range(self._num_forcs):
            pos_chunk_index = 0

            self._current_sho_spec_slice = slice(self.sho_spec_inds_per_forc * self._current_forc,
                                                 self.sho_spec_inds_per_forc * (self._current_forc + 1))
            self._current_met_spec_slice = slice(self.metrics_spec_inds_per_forc * self._current_forc,
                                                 self.metrics_spec_inds_per_forc * (self._current_forc + 1))
            dc_vec = self._get_dc_offset(verbose=verbose)
            '''
            Loop over positions
            '''
            while self._current_pos_slice.stop < self._end_pos:
                loops_2d, nd_mat_shape_dc_first, order_dc_offset_reverse = self._get_projection_data(pos_chunk_index)

                # step 8: perform loop unfolding
                projected_loops_2d, loop_metrics_1d = self._project_loop_batch(dc_vec, np.transpose(loops_2d))

                # test the reshapes back
                projected_loops_2d = self._reshape_projected_loops_for_h5(projected_loops_2d,
                                                                          order_dc_offset_reverse,
                                                                          nd_mat_shape_dc_first)
                self.h5_projected_loops[self._current_pos_slice, self._current_sho_spec_slice] = projected_loops_2d

                metrics_2d = self._reshape_results_for_h5(loop_metrics_1d, nd_mat_shape_dc_first)

                self.h5_loop_metrics[self._current_pos_slice, self._current_met_spec_slice] = metrics_2d

            # Reset the position slice
            self._current_pos_slice = slice(None)

        pass

    def _get_data_chunk(self, verbose=False):
        """
        Get the next chunk of raw data for doing the loop projections.

        Parameters
        ----------
        verbose : Boolean
            Whether or not to print debugging statements
        """
        if self._start_pos < self.max_pos:
            self._current_sho_spec_slice = slice(self.sho_spec_inds_per_forc * self._current_forc,
                                                 self.sho_spec_inds_per_forc * (self._current_forc + 1))
            self._end_pos = int(min(self.h5_main.shape[0], self._start_pos + self.max_pos))
            self.data = self.h5_main[self._start_pos:self._end_pos, self._current_sho_spec_slice]
        elif self._current_forc < self._num_forcs-1:
            # Resest for next FORC
            self._current_forc += 1

            self._current_sho_spec_slice = slice(self.sho_spec_inds_per_forc * self._current_forc,
                                                 self.sho_spec_inds_per_forc * (self._current_forc + 1))
            self._current_met_spec_slice = slice(self.metrics_spec_inds_per_forc * self._current_forc,
                                                 self.metrics_spec_inds_per_forc * (self._current_forc + 1))
            self._get_dc_offset(verbose=verbose)

            self._start_pos = 0
            self._end_pos = int(min(self.h5_main.shape[0], self._start_pos + self.max_pos))
            self.data = self.h5_main[self._start_pos:self._end_pos, self._current_sho_spec_slice]

        else:
            self.data = None

        return

    def _get_guess_chunk(self, verbose=False):
        """
        Read the next chunk of the Guess to use for fitting
        
        Parameters
        ----------
        verbose : Boolean (optional)
            Whether or not to print debugging statements
        """
        if self._start_pos < self.max_pos:
            self._current_sho_spec_slice = slice(self.sho_spec_inds_per_forc * self._current_forc,
                                                 self.sho_spec_inds_per_forc * (self._current_forc + 1))
            self._end_pos = int(min(self.h5_projected_loops.shape[0], self._start_pos + self.max_pos))
            self.data = self.h5_projected_loops[self._start_pos:self._end_pos, self._current_sho_spec_slice]
        elif self._current_forc < self._num_forcs-1:
            # Resest for next FORC
            self._current_forc += 1

            self._current_sho_spec_slice = slice(self.sho_spec_inds_per_forc * self._current_forc,
                                                 self.sho_spec_inds_per_forc * (self._current_forc + 1))
            self._current_met_spec_slice = slice(self.metrics_spec_inds_per_forc * self._current_forc,
                                                 self.metrics_spec_inds_per_forc * (self._current_forc + 1))
            self._get_dc_offset(verbose=verbose)

            self._start_pos = 0
            self._end_pos = int(min(self.h5_projected_loops.shape[0], self._start_pos + self.max_pos))
            self.data = self.h5_projected_loops[self._start_pos:self._end_pos, self._current_sho_spec_slice]

        else:
            self.data = None

        guess = self.h5_guess[self._start_pos:self._end_pos,
                              self._current_met_spec_slice].reshape([-1, 1])
        self.guess = compound_to_scalar(guess)[:, :-1]

    def _create_guess_datasets(self):
        """
        Creates the HDF5 Guess dataset and links the it to the ancillary datasets.
        """
        self.h5_guess = create_empty_dataset(self.h5_loop_metrics, loop_fit32, 'Guess')
        self._h5_group.attrs['guess method'] = 'pycroscopy statistical'

        self.hdf.flush()

    @staticmethod
    def _guess_loops(vdc_vec, projected_loops_2d):
        """
        Provides loop parameter guesses for a given set of loops

        Parameters
        ----------
        vdc_vec : 1D numpy float numpy array
            DC voltage offsets for the loops
        projected_loops_2d : 2D numpy float array
            Projected loops arranged as [instance or position x dc voltage steps]

        Returns
        -------
        guess_parms : 1D compound numpy array
            Loop parameter guesses for the provided projected loops
            
        """

        def _loop_fit_tree(tree, guess_mat, fit_results, vdc_shifted, shift_ind):
            """
            Recursive function that fits a tree object describing the cluster results

            Parameters
            ----------
            tree : ClusterTree object
                Tree describing the clustering results
            guess_mat : 1D numpy float array
                Loop parameters that serve as guesses for the loops in the tree
            fit_results : 1D numpy float array
                Loop parameters that serve as fits for the loops in the tree
            vdc_shifted : 1D numpy float array
                DC voltages shifted be 1/4 cycle
            shift_ind : unsigned int
                Number of units to shift loops by

            Returns
            -------
            guess_mat : 1D numpy float array
                Loop parameters that serve as guesses for the loops in the tree
            fit_results : 1D numpy float array
                Loop parameters that serve as fits for the loops in the tree
                
            """
            # print('Now fitting cluster #{}'.format(tree.name))
            # I already have a guess. Now fit myself
            curr_fit_results = fit_loop(vdc_shifted, np.roll(tree.value, shift_ind), guess_mat[tree.name])
            # keep all the fit results
            fit_results[tree.name] = curr_fit_results
            for child in tree.children:
                # Use my fit as a guess for the lower layers:
                guess_mat[child.name] = curr_fit_results[0].x
                # Fit this child:
                guess_mat, fit_mat = _loop_fit_tree(child, guess_mat, fit_results, vdc_shifted, shift_ind)
            return guess_mat, fit_results

        num_clusters = max(2, int(projected_loops_2d.shape[0] ** 0.5))  # change this to 0.6 if necessary
        estimators = KMeans(num_clusters)
        results = estimators.fit(projected_loops_2d)
        centroids = results.cluster_centers_
        labels = results.labels_

        # Get the distance between cluster means
        distance_mat = pdist(centroids)
        # get hierarchical pairings of clusters
        linkage_pairing = linkage(distance_mat, 'weighted')
        # Normalize the pairwise distance with the maximum distance
        linkage_pairing[:, 2] = linkage_pairing[:, 2] / max(linkage_pairing[:, 2])

        # Now use the tree class:
        cluster_tree = ClusterTree(linkage_pairing[:, :2], labels,
                                   distances=linkage_pairing[:, 2],
                                   centroids=centroids)
        num_nodes = len(cluster_tree.nodes)

        # prepare the guess and fit matrices
        loop_guess_mat = np.zeros(shape=(num_nodes, 9), dtype=np.float32)
        # loop_fit_mat = np.zeros(shape=loop_guess_mat.shape, dtype=loop_guess_mat.dtype)
        loop_fit_results = list(np.arange(num_nodes, dtype=np.uint16))  # temporary placeholder

        shift_ind, vdc_shifted = BELoopModel.shift_vdc(vdc_vec)

        # guess the top (or last) node
        loop_guess_mat[-1] = generate_guess(vdc_vec, cluster_tree.tree.value)

        # Now guess the rest of the tree
        loop_guess_mat, loop_fit_results = _loop_fit_tree(cluster_tree.tree, loop_guess_mat, loop_fit_results,
                                                          vdc_shifted, shift_ind)

        # Prepare guesses for each pixel using the fit of the cluster it belongs to:
        guess_parms = np.zeros(shape=projected_loops_2d.shape[0], dtype=loop_fit32)
        for clust_id in range(num_clusters):
            pix_inds = np.where(labels == clust_id)[0]
            temp = np.atleast_2d(loop_fit_results[clust_id][0].x)
            # convert to the appropriate dtype as well:
            r2 = 1-np.sum(np.abs(loop_fit_results[clust_id][0].fun**2))
            guess_parms[pix_inds] = realToCompound(np.hstack([temp, np.atleast_2d(r2)]), loop_fit32)

        return guess_parms

    @staticmethod
    def shift_vdc(vdc_vec):
        """
        Rolls the Vdc vector by a quarter cycle

        Parameters
        ----------
        vdc_vec : 1D numpy array
            DC offset vector
            
        Returns
        -------
        shift_ind : int
            Number of indices by which the vector was rolled
        vdc_shifted : 1D numpy array
            Vdc vector rolled by a quarter cycle
            
        """
        shift_ind = int(-1 * len(vdc_vec) / 4)  # should NOT be hardcoded like this!
        vdc_shifted = np.roll(vdc_vec, shift_ind)
        return shift_ind, vdc_shifted

    def _create_fit_dataset(self):
        """
        Creates the HDF5 Fit dataset and links the it to the ancillary datasets.
        """

        if self.h5_guess is None:
            warn('Need to guess before fitting!')
            return

        self.h5_fit = create_empty_dataset(self.h5_guess, loop_fit32, 'Fit')
        self._h5_group.attrs['fit method'] = 'pycroscopy functional'

    def _reformat_results(self, results, strategy='BE_LOOP', verbose=False):
        """
        Reformat loop fit results to target compound dataset

        Parameters
        ----------
        results : list
            list of loop fit / guess results objects
        strategy : string / unicode (optional)
            Name of the computational strategy
        verbose : Boolean (optional)
            Whether or not to print debugging statements

        Returns
        -------
        temp : 1D compound array
            An array of the loop parameters in the target compound datatype
            
        """
        if verbose:
            print('Strategy to use: {}'.format(strategy))
        # Create an empty array to store the guess parameters
        if verbose:
            print('Raw results and compound Loop vector of shape {}'.format(len(results)))

        if strategy in ['BE_LOOP']:
            temp = np.array([np.hstack([result.x, result.fun]) for result in results])
            temp = realToCompound(temp, loop_fit32)
        return temp


class LoopOptimize(Optimize):
    """
    Subclass of Optimize with BE Loop specific changes 
    """
    def _initiateSolverAndObjFunc(self):
        if self.solver_type in scipy.optimize.__dict__.keys():
            solver = scipy.optimize.__dict__[self.solver_type]
        if self.obj_func is None:
            fm = BE_Fit_Methods()
            func = fm.__getattribute__(self.obj_func_name)(self.obj_func_xvals)
        return solver, self.solver_options, func
