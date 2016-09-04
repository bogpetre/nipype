from scipy.linalg import svd # singular value decomposition
from ..interfaces.base import BaseInterfaceInputSpec, TraitedSpec, \
    BaseInterface, traits, File
import nibabel as nb
import numpy as np
import os

from nipype.pipeline.engine import Workflow

class CompCoreInputSpec(BaseInterfaceInputSpec):
    realigned_file = File(exists=True, mandatory=True, desc='already realigned brain image (4D)')
    mask_file = File(exists=True, mandatory=True, desc='mask file that determines ROI (3D)')
    num_components = traits.Int(default=6) # 6 for BOLD, 4 for ASL
    # additional_regressors??

class CompCoreOutputSpec(TraitedSpec):
    components_file = File(desc='text file containing the noise components', exists=True)

class CompCore(BaseInterface):
    '''
    Interface with core CompCor computation, used in aCompCor and tCompCor

    Example
    -------

    >>> ccinterface = CompCore()
    >>> ccinterface.inputs.realigned_file = 'nipype/testing/data/functional.nii'
    >>> ccinterface.inputs.mask_file = 'nipype/testing/data/mask.nii'
    >>> ccinterface.inputs.num_components = 1
    '''
    input_spec = CompCoreInputSpec
    output_spec = CompCoreOutputSpec

    def _run_interface(self, runtime):
        imgseries = nb.load(self.inputs.realigned_file).get_data()
        mask = nb.load(self.inputs.mask_file).get_data()
        voxel_timecourses = imgseries[mask > 0]
        # Zero-out any bad values
        voxel_timecourses[np.isnan(np.sum(voxel_timecourses, axis=1)), :] = 0

        # from paper:
        # "Voxel time series from the noise ROI (either anatomical or tSTD) were
        # placed in a matrix M of size Nxm, with time along the row dimension
        # and voxels along the column dimension."
        # voxel_timecourses.shape == [nvoxels, time]
        M = voxel_timecourses.T

        # "The constant and linear trends of the columns in the matrix M were removed ..."
        M = (M - np.mean(M, axis=0))

        # "... prior to column-wise variance normalization."
        stdM = np.std(M, axis=0)
        # set bad values to division identity
        stdM[stdM == 0] = 1.
        stdM[np.isnan(stdM)] = 1.
        stdM[np.isinf(stdM)] = 1.
        M = M / stdM

        # "The covariance matrix C = MMT was constructed and decomposed into its
        # principal components using a singular value decomposition."
        u, _, _ = svd(M, full_matrices=False)

        components = u[:, :self.inputs.num_components]
        components_file = os.path.join(os.getcwd(), "components_file.txt")
        np.savetxt(components_file, components, fmt="%.10f")
        return runtime

class aCompCor(Workflow):
    pass

class tCompCor(Workflow):
    pass
