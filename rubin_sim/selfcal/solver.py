import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import lsqr

# Modified from /astro/store/scratch/tmp/yoachim/Research/LSST/Parallel_Solver
# and then from https://github.com/lsst-sims/legacy_sims_selfcal


class LsqrSolver(object):
    """
    Class to read in the output from genCatalog.py and run the self-calibration solver and write the output.

    Might want to expand this so it can be used to fit an arbitrary number of terms?
    """

    def __init__(
        self,
        observations,
        patch_out="solved_patches.npz",
        star_out="solved_stars.npz",
        atol=1e-8,
        btol=1e-8,
        iter_lim=None,
    ):
        """
        patch_out: filename for saving the patch zeropoints
        star_out: filename for saving the star solutions
        atol: tolerance for the solver
        btol: tolerance for the solver
        """
        self.patch_out = patch_out
        self.star_out = star_out
        self.atol = atol
        self.btol = btol
        self.iter_lim = iter_lim
        self.observations = observations

    def run(self):
        self.clean_data()
        self.solve_matrix()
        self.write_soln()

    def clean_data(self):
        """
        Remove observations that can't contribute to a solution.
        Index remaining stars and patches so they are continuous.
        """
        nStart = 1.0
        nEnd = 0.0
        while nStart != nEnd:
            nStart = self.observations.size
            self.observations.sort(order="id")
            # Remove observations if the star was only observed once
            good = np.where(
                (self.observations["id"] - np.roll(self.observations["id"], 1))
                * (self.observations["id"] - np.roll(self.observations["id"], -1))
                == 0
            )
            self.observations = self.observations[good]

            # Remove patches with only one star
            self.observations.sort(order="patch_id")

            good = np.where(
                (
                    self.observations["patch_id"]
                    - np.roll(self.observations["patch_id"], 1)
                )
                * (
                    self.observations["patch_id"]
                    - np.roll(self.observations["patch_id"], -1)
                )
                == 0
            )
            self.observations = self.observations[good]
            nEnd = self.observations.size

        self.observations.sort(order="patch_id")

        self.Patches = np.unique(self.observations["patch_id"])
        nPatches = np.size(self.Patches)
        self.nPatches = nPatches
        self.nPatches = nPatches
        Patches_index = np.arange(nPatches)
        left = np.searchsorted(self.observations["patch_id"], self.Patches)
        right = np.searchsorted(
            self.observations["patch_id"], self.Patches, side="right"
        )
        for i in range(np.size(left)):
            self.observations["patch_id"][left[i] : right[i]] = Patches_index[i]

        # Convert id to continuous running index to keep matrix as small as possible
        self.observations.sort(order="id")
        self.Stars = np.unique(self.observations["id"])
        nStars = np.size(self.Stars)
        self.nStars = nStars
        Stars_index = np.arange(1, nStars + 1)
        left = np.searchsorted(self.observations["id"], self.Stars)
        right = np.searchsorted(self.observations["id"], self.Stars, side="right")
        for i in range(np.size(left)):
            self.observations["id"][left[i] : right[i]] = Stars_index[i]

    def solve_matrix(self):
        nObs = np.size(self.observations)
        # construct sparse matrix
        # A = lil_matrix((nPatches+nStars,np.size(observations['patch_id'])))
        row = np.arange(nObs)
        row = np.append(row, row)
        col = np.append(
            self.observations["patch_id"],
            self.observations["id"] + np.max(self.observations["patch_id"]),
        )
        # data = np.append(np.ones(nObs),1./observations['mag_uncert'])
        data = 1.0 / self.observations["mag_uncert"]
        data = np.append(data, data)
        b = (
            self.observations["observed_mag"] / self.observations["mag_uncert"]
        )  # maybe do this in place earlier?  then I can just delete parts of observations earlier to save total memory

        # blast away data now that we have the matrix constructed
        del self.observations

        A = coo_matrix((data, (row, col)), shape=(nObs, self.nPatches + self.nStars))
        A = A.tocsr()
        # solve Ax = b
        self.solution = lsqr(
            A, b, show=True, atol=self.atol, btol=self.btol, iter_lim=self.iter_lim
        )

    def return_solution(self):
        patches = np.empty(
            self.Patches.size, dtype=list(zip(["patch_id", "zp"], [int, float]))
        )
        patches["patch_id"] = self.Patches
        patches["zp"] = self.solution[0][0 : self.nPatches]

        stars = np.empty(
            self.Stars.size, dtype=list(zip(["id", "fit_mag"], [int, float]))
        )
        stars["id"] = self.Stars
        stars["fit_mag"] = self.solution[0][self.nPatches :]

        return patches, stars

    def write_soln(self):
        patches, stars = self.return_solution()
        if self.patch_out is not None:
            np.savez(self.patch_out, result=patches)
        if self.star_out is not None:
            np.savez(self.star_out, result=stars)
