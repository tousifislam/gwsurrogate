""" Gravitational Wave Surrogate classes for text and hdf5 files"""

from __future__ import division

__copyright__ = "Copyright (C) 2014 Scott Field and Chad Galley"
__email__     = "sfield@astro.cornell.edu, crgalley@tapir.caltech.edu"
__status__    = "testing"
__author__    = "Scott Field, Chad Galley"

__license__ = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import numpy as np
from scipy.interpolate import splrep
from scipy.interpolate import splev
from harmonics import sYlm as sYlm
import const_mks as mks
import gwtools
import matplotlib.pyplot as plt
import time
import os as os
from parametric_funcs import function_dict as my_funcs
from surrogateIO import H5Surrogate, TextSurrogateRead, TextSurrogateWrite

try:
	import h5py
	h5py_enabled = True
except ImportError:
	h5py_enabled = False


# needed to search for single mode surrogate directories 
def list_folders(path,prefix):
        '''returns all folders which begin with some prefix'''
        for f in os.listdir(path):
                if f.startswith(prefix):
                        yield f

# handy helper to save waveforms 
def write_waveform(t, hp, hc, filename='output',ext='bin'):
  """write waveform to text or numpy binary file"""

  if( ext == 'txt'):
    np.savetxt(filename, [t, hp, hc])
  elif( ext == 'bin'):
    np.save(filename, [t, hp, hc])
  else:
    raise ValueError('not a valid file extension')


##############################################
class ExportSurrogate(H5Surrogate, TextSurrogateWrite):
	"""Export single-mode surrogate"""
	
	#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
	def __init__(self, path):
		
		# export HDF5 or Text surrogate data depending on input file extension
		ext = path.split('.')[-1]
		if ext == 'hdf5' or ext == 'h5':
			H5Surrogate.__init__(self, file=path, mode='w')
		else:
			raise ValueError('use TextSurrogateWrite instead')


##############################################
class EvaluateSingleModeSurrogate(H5Surrogate, TextSurrogateRead):
  """Evaluate single-mode surrogate in terms of the waveforms' amplitude and phase"""

  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def __init__(self, path, deg=3, subdir='', closeQ=True):
    
    # Load HDF5 or Text surrogate data depending on input file extension
    if type(path) == h5py._hl.files.File:
      ext = 'h5'
    else:
      ext = path.split('.')[-1]
    if ext == 'hdf5' or ext == 'h5':
      H5Surrogate.__init__(self, file=path, mode='r', subdir=subdir, closeQ=closeQ)
    else:
      TextSurrogateRead.__init__(self, path)
    
    # Interpolate columns of the empirical interpolant operator, B, using cubic spline
    if self.surrogate_mode_type  == 'waveform_basis':
      self.reB_spline_params = [splrep(self.times, self.B[:,jj].real, k=deg) for jj in range(self.dim_rb)]
      self.imB_spline_params = [splrep(self.times, self.B[:,jj].imag, k=deg) for jj in range(self.dim_rb)]
    elif self.surrogate_mode_type  == 'amp_phase_basis':
      self.B1_spline_params = [splrep(self.times, self.B_1[:,jj], k=deg) for jj in range(self.B_1.shape[1])]
      self.B2_spline_params = [splrep(self.times, self.B_2[:,jj], k=deg) for jj in range(self.B_2.shape[1])]
    else:
      raise ValueError('invalid surrogate type')

    # Convenience for plotting purposes
    self.plt = plt
    self.plot_pretty = gwtools.plot_pretty

    # All surrogates are dimensionless - this tag enforces this and could be generalized 
    self.surrogate_units = 'dimensionless'
    
    pass

  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def __call__(self, q, M=None, dist=None, phi_ref=None,\
                     f_low=None, samples=None,samples_units='dimensionless'):
    """Return single mode surrogate evaluation for...

       Input
       =====
       q             --- mass ratio (dimensionless) 
       M             --- total mass (solar masses) 
       dist          --- distance to binary system (megaparsecs)
       phir          --- mode's phase at peak amplitude
       flow          --- instantaneous initial frequency, will check if flow_surrogate < flow 
       samples       --- array of dimensionless times at which surrogate is to be evaluated
       samples_units --- units (mks or dimensionless) of input array samples


       More information
       ================
       This routine evaluates gravitational wave complex polarization modes h_{ell m}
       defined on a sphere whose origin is the binary's center of mass. 

       Dimensionless surrogates rh/M are evaluated by calling _h_sur. 
       Physical surrogates are generated by applying additional operations/scalings.

       If M and dist are provided, a physical surrogate will be returned in mks units.

       An array of times can be passed along with its units. """

    # surrogate evaluations assumed dimensionless, physical modes are found from scalings 
    if self.surrogate_units != 'dimensionless':
      raise ValueError('surrogate units is not supported')

    if (samples_units != 'dimensionless') and (samples_units != 'mks'):
      raise ValueError('samples_units is not supported')

    ### compute surrogate's parameter values from input ones (q,M) ###
    # Ex: symmetric mass ratio x = q / (1+q)^2 might parameterize the surrogate
    x = self.get_surr_params(q)

    ### if (M,distance) provided, a physical mode in mks units is returned ###
    if( M is not None and dist is not None):
      amp0    = ((M * mks.Msun ) / (dist * mks.Mpcinm )) * ( mks.G / np.power(mks.c,2.0) )
      t_scale = mks.Msuninsec * M
    else:
      amp0    = 1.0
      t_scale = 1.0

    ### evaluation times t: input times or times at which surrogate was built ###
    if (samples is not None):
      t = samples
    else:
      t = self.time()

    ### if input times are dimensionless, convert to MKS if a physical surrogate is requested ###
    if samples_units == 'dimensionless':
      t = t_scale * t

    # because samples is passed to _h_sur, it must be dimensionless form t/M
    if samples is not None and samples_units == 'mks':
      samples = samples / t_scale

    ### Evaluate dimensionless single mode surrogates ###
    hp, hc = self._h_sur(x, samples=samples)

    ### adjust mode's phase by an overall constant ###
    if (phi_ref is not None):
      h  = self.adjust_merger_phase(hp + 1.0j*hc,phi_ref)
      hp = h.real
      hc = h.imag


    ### Restore amplitude scalings ###
    hp     = amp0 * hp
    hc     = amp0 * hc

    ### check that surrogate's starting frequency is below f_low, otherwise throw a warning ###
    if f_low is not None:
      self.find_instant_freq(hp, hc, t, f_low)

    return t, hp, hc


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def find_instant_freq(self, hp, hc, t, f_low = None):
    """instantaneous frequency at t_start for 

          h = A(t) exp(2 * pi * i * f(t) * t), 

       where \partial_t A ~ \partial_t f ~ 0. If f_low passed will check its been achieved."""

    f_instant = gwtools.find_instant_freq(hp, hc, t)

    if f_low is None:
      return f_instant
    else:
      if f_instant > f_low:
        raise Warning, "starting frequency is "+str(f_instant)
      else:
        pass


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def amp_phase(self,h):
    """Get amplitude and phase of waveform, h = A*exp(i*phi)"""
    return gwtools.amp_phase(h)


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def phi_merger(self,h):
    """Phase of mode at amplitude's discrete peak. h = A*exp(i*phi)."""

    amp, phase = self.amp_phase(h)
    argmax_amp = np.argmax(amp)

    return phase[argmax_amp]


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def adjust_merger_phase(self,h,phiref):
    """Modify GW mode's phase such that at time of amplitude peak, t_peak, we have phase(t_peak) = phiref"""

    phimerger = self.phi_merger(h)
    phiadj    = phiref - phimerger

    return gwtools.modify_phase(h,phiadj)


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def timer(self,M_eval=None,dist_eval=None,phi_ref=None,f_low=None,samples=None):
    """average time to evaluate surrogate waveforms. """

    qmin, qmax = self.fit_interval
    ran = np.random.uniform(qmin, qmax, 1000)

    tic = time.time()
    if M_eval is None:
      for i in ran:
        hp, hc = self._h_sur(i)
    else:
      for i in ran:
        t, hp, hc = self.__call__(i,M_eval,dist_eval,phi_ref,f_low,samples)

    toc = time.time()
    print 'Timing results (results quoted in seconds)...'
    print 'Total time to generate 1000 waveforms = ',toc-tic
    print 'Average time to generate a single waveform = ', (toc-tic)/1000.0
    pass

	
  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def time(self, units=None,M=None):
    """Return time samples at which the surrogate was built for.

      INPUT
      =====
      units --- None:        time in geometric units, G=c=1
                'mks'        time in seconds
                'solarmass': time in solar masses
      M     --- Mass in units of solar masses. Must be provided if units='mks'"""

    if units is None:
      t = self.times
    elif units == 'solarmass':
      t = mks.Msuninsec * self.times
    elif units == 'mks':
      t = (mks.Msuninsec*M) * self.times
    return t

	
  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def basis(self, i, flavor='waveform'):
    """compute the ith cardinal, orthogonal, or waveform basis."""

    # TODO: need to gaurd against missing V,R and their relationships to B (or B_1, B_2)

    if flavor == 'cardinal':
      basis = self.B[:,i]
    elif flavor == 'orthogonal':
      basis = np.dot(self.B,self.V)[:,i]
    elif flavor == 'waveform':
      E = np.dot(self.B,self.V)
      basis = np.dot(E,self.R)[:,i]
    else:
      raise ValueError("Not a valid basis type")

    return basis


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def resample_B(self, samples):
    """resample the empirical interpolant operator, B, at the input samples"""
    return np.array([splev(samples, self.reB_spline_params[jj])  \
             + 1j*splev(samples, self.imB_spline_params[jj]) for jj in range(self.dim_rb)]).T


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def plot_rb(self, i, showQ=True):
    """plot the ith reduced basis waveform"""

    # NOTE: Need to allow for different time units for plotting and labeling

    # Compute surrogate approximation of RB waveform
    basis = self.basis(i)
    hp    = basis.real
    hc    = basis.imag
    
    # Plot waveform
    fig = self.plot_pretty(self.times,hp,hc)

    if showQ:
      self.plt.show()
    
    # Return figure method to allow for saving plot with fig.savefig
    return fig


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def plot_sur(self, q_eval, timeM=False, htype='hphc', flavor='linear', color='k', linestyle=['-', '--'], \
                label=['$h_+(t)$', '$h_-(t)$'], legendQ=False, showQ=True):
    """plot surrogate evaluated at mass ratio q_eval"""

    t, hp, hc = self.__call__(q_eval)
    h = hp + 1j*hc
    
    y = {
      'hphc': [hp, hc],
      'hp': hp,
      'hc': hc,
      'AmpPhase': [np.abs(h), gwtools.phase(h)],
      'Amp': np.abs(h),
      'Phase': gwtools.phase(h),
      }
    
    if self.t_units == 'TOverMtot':
      xlab = 'Time, $t/M$'
    else:
      xlab = 'Time, $t$ (sec)'

    # Plot surrogate waveform
    fig = self.plot_pretty(t, y[htype], flavor=flavor, color=color, linestyle=linestyle, \
                label=label, legendQ=legendQ, showQ=False)
    self.plt.xlabel(xlab)
    self.plt.ylabel('Surrogate waveform')
    
    if showQ:
      self.plt.show()
        
    # Return figure method to allow for saving plot with fig.savefig
    return fig
  
  
  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def plot_eim_data(self, inode=None, htype='Amp', nuQ=False, fignum=1, showQ=True):
    """Plot empirical interpolation data used for performing fits in parameter"""
    
    fig = self.plt.figure(fignum)
    ax1 = fig.add_subplot(111)
    
    y = {
      'Amp': self.eim_amp,
      'Phase': self.eim_phase,
      }
    
    if nuQ:
      nu = gwtools.q_to_nu(self.greedy_points)
      
      if inode is None:
        [self.plt.plot(nu, ee, 'ko') for ee in y[htype]]
      else:
        self.plt.plot(nu, y[htype][inode], 'ko')
      
      self.plt.xlabel('Symmetric mass ratio, $\\nu$')
    
    else:
      
      if inode is None:
        [self.plt.plot(self.greedy_points, ee, 'ko') for ee in y[htype]]
      else:
        self.plt.plot(self.greedy_points, y[htype][inode], 'ko')
      
      self.plt.xlabel('Mass ratio, $q$')
    
    if showQ:
      self.plt.show()
    
    return fig
  
  
  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def plot_eim_fits(self, inode=None, htype='Amp', nuQ=False, fignum=1, num=200, showQ=True):
    """Plot empirical interpolation data and fits"""
    
    fig = self.plt.figure(fignum)
    ax1 = fig.add_subplot(111)
    
    fitfn = {
      'Amp': self.amp_fit_func,
      'Phase': self.phase_fit_func,
      }
    
    coeffs = {
      'Amp': self.fitparams_amp,
      'Phase': self.fitparams_phase,
      }
    
    # Plot EIM data points
    self.plot_eim_data(inode=inode, htype=htype, nuQ=nuQ, fignum=fignum, showQ=False)
    
    qs = np.linspace(self.fit_min, self.fit_max, num)
    nus = gwtools.q_to_nu(qs)
    
    # Plot fits to EIM data points
    if nuQ:
      if inode is None:
        [self.plt.plot(nus, fitfn[htype](cc, qs), 'k-') for cc in coeffs[htype]]
      else:
        self.plt.plot(nus, fitfn[htype](coeffs[htype][inode], qs), 'k-')  
    
    else:
      if inode is None:
        [self.plt.plot(qs, fitfn[htype](cc, qs), 'k-') for cc in coeffs[htype]]
      else:
        self.plt.plot(qs, fitfn[htype](coeffs[htype][inode], qs), 'k-')
      
    if showQ:
      self.plt.show()
    
    return fig
  
  
  #### below here are "private" member functions ###
  # These routine's evaluate a "bare" surrogate, and should only be called
  # by the __call__ method 
  #
  # These routine's use x as the parameter, which could be mass ratio,
  # symmetric mass ratio, or something else. Parameterization info should
  # be supplied by surrogate's parameterization tag.

  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def _affine_mapper_checker(self, x):
    """map parameter value x to the standard interval [-1,1] if necessary. 
       Check if x within training interval."""

    x_min, x_max = self.fit_interval

    if( x < x_min or x > x_max):
      print "Warning: Surrogate not trained at requested parameter value" # needed to display in ipython notebook
      Warning("Surrogate not trained at requested parameter value")


    # TODO: should be rolled like amp/phase/fit funcs
    # QUESTION FOR SCOTT: Why not just make self.affine_map the end points [a,b] 
    #and map that to self.fit_interval? (and keep the 'none' bit or use None directly)
    if self.affine_map == 'minus1_to_1':
      x_0 = 2.*(x - x_min)/(x_max - x_min) - 1.;
    elif self.affine_map == 'zero_to_1':
      x_0 = (x - x_min)/(x_max - x_min);
    elif self.affine_map == 'none':
      x_0 = x
    else:
      raise ValueError('unknown affine map')
    return x_0

  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def _norm_eval(self, x_0, affine_mapped=True):
    """evaluate norm fit at x_0"""

    if not self.norms:
      return 1.

    # TODO: this seems hacky -- just so when calling from outside class (which shouldn't be done) it will evaluate correctly
    # TODO: need to gaurd against missing norm info
    if( not(affine_mapped) ):
      x_0 = self._affine_mapper_checker(x_0)

    nrm_eval  = np.array([ self.norm_fit_func(self.fitparams_norm, x_0) ])
    return nrm_eval


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def _amp_eval(self, x_0):
    """evaluate amplitude fit at x_0"""
    # 0:self.dim_rb... could be bad: fit degrees of freedom have nothing to do with rb dimension
    #return np.array([ self.amp_fit_func(self.fitparams_amp[jj, 0:self.dim_rb], x_0) for jj in range(self.dim_rb) ])
    #return np.array([ self.amp_fit_func(self.fitparams_amp[jj,:], x_0) for jj in range(self.dim_rb) ])
    # TODO: How slow is shape?
    return np.array([ self.amp_fit_func(self.fitparams_amp[jj,:], x_0) for jj in range(self.fitparams_amp.shape[0]) ])


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def _phase_eval(self, x_0):
    """evaluate phase fit at x_0"""
    #return np.array([ self.phase_fit_func(self.fitparams_phase[jj, 0:self.dim_rb], x_0) for jj in range(self.dim_rb) ])
    #return np.array([ self.phase_fit_func(self.fitparams_phase[jj,:], x_0) for jj in range(self.dim_rb) ])
    return np.array([ self.phase_fit_func(self.fitparams_phase[jj,:], x_0) for jj in range(self.fitparams_phase.shape[0]) ])


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def _h_sur(self, x, samples=None):
    """Evaluate surrogate at parameter value x. x could be mass ratio, symmetric
       mass ratio or something else -- it depends on the surrogate's parameterization. 

       Returns dimensionless rh/M waveforms in units of t/M.

       This should ONLY be called by the __call__ method which accounts for 
       different parameterization choices. """

    ### Map q to the standard interval and check parameter validity ###
    x_0 = self._affine_mapper_checker(x)

    ### Evaluate amp/phase/norm fits ###
    amp_eval   = self._amp_eval(x_0)
    phase_eval = self._phase_eval(x_0)
    nrm_eval   = self._norm_eval(x_0)

    if self.surrogate_mode_type  == 'waveform_basis':

      ### Build dim_RB-vector fit evaluation of h ###
      h_EIM = amp_eval*np.exp(1j*phase_eval)
		
      if samples == None:
        surrogate = np.dot(self.B, h_EIM)
      else:
        surrogate = np.dot(self.resample_B(samples), h_EIM)


    elif self.surrogate_mode_type  == 'amp_phase_basis':

      if samples == None:
        sur_A = np.dot(self.B_1, amp_eval)
        sur_P = np.dot(self.B_2, phase_eval)
      else:
        sur_A = np.dot(np.array([splev(samples, self.B1_spline_params[jj]) for jj in range(self.B_1.shape[1])]).T, amp_eval)
        sur_P = np.dot(np.array([splev(samples, self.B2_spline_params[jj]) for jj in range(self.B_2.shape[1])]).T, phase_eval)

      surrogate = sur_A*np.exp(1j*sur_P)


    else:
      raise ValueError('invalid surrogate type')


    surrogate = nrm_eval * surrogate
    hp = surrogate.real
    #hp = hp.reshape([self.time_samples,])
    hc = surrogate.imag
    #hc = hc.reshape([self.time_samples,])

    return hp, hc


##############################################
class EvaluateSurrogate(EvaluateSingleModeSurrogate): 
# TODO: inherated from EvalSingleModeSurrogate to gain access to some functions. this should be better structured
  """Evaluate multi-mode surrogates"""

  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def __init__(self, path, deg=3):
    
    # Make list of required data for reading/writing surrogate data
    self.required = ['tmin', 'tmax', 'greedy_points', 'eim_indices', 'B', \
                     'fitparams_amp', 'fitparams_phase', \
                     'fit_min', 'fit_max', 'fit_type_amp', 'fit_type_phase', \
                     'surrogate_mode_type', 'parameterization']
    
    # Convenience for plotting purposes
    self.plt = plt

    ### fill up dictionary with single mode surrogate class ###
    self.single_modes = dict()

    # Load HDF5 or Text surrogate data depending on input file extension
    if type(path) == h5py._hl.files.File:
      ext = 'h5'
      filemode = path.mode
    else:
      ext = path.split('.')[-1]
      filemode = 'r'

    if ext == 'hdf5' or ext == 'h5':
      
      if filemode not in ['r+', 'w']:
        fp = h5py.File(path, filemode)
        
        ### compile list of available modes ###
        mode_keys = []
        for kk in fp.keys():
          splitkk = kk.split('_')
          if splitkk[0][0] == 'l' and splitkk[1][0] == 'm':
            #mode_keys.append(kk)
            ell = int(splitkk[0][1])
            emm = int(splitkk[1][1:])
            mode_keys.append((ell,emm))
        for mode_key in mode_keys:
          mode_key_str = 'l'+str(mode_key[0])+'_m'+str(mode_key[1])
          print "loading surrogate mode... " + mode_key_str
          self.single_modes[mode_key] = EvaluateSingleModeSurrogate(fp, subdir=mode_key_str+'/', closeQ=False)
        fp.close()
        
        self.modes = mode_keys
      
    else:
      ### compile list of available modes ###
      # assumes (i) single mode folder format l#_m#_ 
      #         (ii) ell<=9, m>=0
      for single_mode in list_folders(path,'l'):
        #mode_key = single_mode[0:5]
        ell = int(single_mode[1])
        emm = int(single_mode[4])
        mode_key = (ell,emm)
        print "loading surrogate mode... "+single_mode[0:5]
        self.single_modes[mode_key] = EvaluateSingleModeSurrogate(path+single_mode+'/')

    ### Assumes all modes are defined on the same temporal grid. ###
    ### TODO: should explicitly check this in previous step ###
    if filemode not in ['r+', 'w']:
      
      if len(self.single_modes) == 0:
        raise IOError('no surrogate modes found. make sure each mode subdirectory is of the form l#_m#_')
      
      self.time_all_modes = self.single_modes[mode_key].time
          

  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def __call__(self, q, M=None, dist=None, theta=None,phi=None,\
                     phi_ref=None, f_low=None, samples=None,samples_units='dimensionless',\
                     ell=None, m=None, mode_sum=True,fake_neg_modes=False):
    """Return surrogate evaluation for...

      INPUT
      =====
      q              --- mass ratio (dimensionless) 
      M              --- total mass (solar masses) 
      dist           --- distance to binary system (megaparsecs)
      theta/phi      --- evaluate hp and hc modes at this location on sphere
      phir           --- mode's phase at peak amplitude
      flow           --- instantaneous initial frequency, will check if flow_surrogate < flow 
      ell            --- list or array of N ell modes to evaluate for (if none, all modes are returned)
      m              --- for each ell, supply a matching m value 
      mode_sum       --- if true, all modes are summed, if false all modes are returned in an array
      fake_neg_modes --- if true, include m<0 modes deduced from m>0 mode. all m in [ell,m] input should be non-negative

      NOTE: if only requesting one mode, this should be ell=[2],m=[2]

       Note about Angles
       =================
       For circular orbits, the binary's orbital angular momentum is taken to
       be the z-axis. Theta and phi is location on the sphere relative to this 
       coordiante system. """


    if phi_ref is not None:
      raise ValueError('not coded yet')

    ### deduce single mode dictionary keys from ell,m input ###
    modes_to_evaluate = self.generate_mode_eval_list(ell,m,fake_neg_modes)

    ### if mode_sum false, return modes in a sensible way ###
    if not mode_sum:
      modes_to_evaluate = self.sort_mode_list(modes_to_evaluate)

    ### by default, m<0 included as potentially available for evaluation ###
    avail_modes = self.all_model_modes(True)

    ### allocate arrays for multimode polarizations ###
    if mode_sum:
      hp_full, hc_full = self._allocate_output_array(samples,1)
    else:
      hp_full, hc_full = self._allocate_output_array(samples,len(modes_to_evaluate))

    ### loop over all evaluation modes ###
    ii = 0
    for ell,m in modes_to_evaluate:

      ### if the mode is modelled, evaluate it. Otherwise its zero ###
      if (ell,m) in avail_modes:

        if m>=0:
          t_mode, hp_mode, hc_mode = self.evaluate_single_mode(q,M,dist,phi_ref,f_low,samples,samples_units,ell,m)
        else:
          t_mode, hp_mode, hc_mode = self.evaluate_single_mode_minus(q,M,dist,phi_ref,f_low,samples,samples_units,ell,m)

        # TODO: should be faster. integrate this later on
        #if fake_neg_modes and m != 0:
        #  hp_mode_mm, hc_mode_mm = self._generate_minus_m_mode(hp_mode,hc_mode,ell,m)
        #  hp_mode_mm, hc_mode_mm = self.evaluate_on_sphere(ell,-m,theta,phi,hp_mode_mm,hc_mode_mm)

        hp_mode, hc_mode = self.evaluate_on_sphere(ell,m,theta,phi,hp_mode,hc_mode)

        if mode_sum:
          hp_full = hp_full + hp_mode
          hc_full = hc_full + hc_mode
          #if fake_neg_modes and m != 0:
          #  hp_full = hp_full + hp_mode_mm
          #  hc_full = hc_full + hc_mode_mm
        else:
          hp_full[:,ii] = hp_mode[:]
          hc_full[:,ii] = hc_mode[:]

      
      ii+=1

    if mode_sum:
      return t_mode, hp_full, hc_full #assumes all mode's have same temporal grid
    else: # helpful to have (l,m) list for understanding mode evaluations
      return modes_to_evaluate, t_mode, hp_full, hc_full


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def h_sphere_builder(self, q, M=None,dist=None,ell=None,m=None):
    """Returns a function for evaluations of h(t,theta,phi;q,M,d). This new function 
       can be evaluated for rotations about z-axis, and at points on the sphere.

       modes_to_evalute and max/min times defining the surrogate are also returned"""

    modes_to_evaluate, t_mode, hp_full, hc_full = \
      self(q=q, M=M, dist=dist,ell=ell,m=m,mode_sum=False,fake_neg_modes=True)

    ### fill dictionary with model's modes as a spline ###
    hp_modes_spline = dict()
    hc_modes_spline = dict()
    ii = 0
    for ell_m in modes_to_evaluate:
      hp_modes_spline[ell_m] = splrep(t_mode, hp_full[:,ii], k=3)
      hc_modes_spline[ell_m] = splrep(t_mode, hc_full[:,ii], k=3)
      ii += 1

    ### time interval for valid surrogate evaluations ###
    t_min = t_mode.min() 
    t_max = t_mode.max()
 

    ### create function which can be used to evaluate for h(t,theta,phi) ###
    def h_sphere(times,theta=None,phi=None,z_rot=None,psi_rot=None):
      """ evaluations h(t,theta,phi), defined as matrix of modes, or sphere evaluations.

          INPUT
          =====
          times     --- numpy array of times for which the surrogate is defined
          theta/phi --- angle on the sphere, evaluations after z-axis rotation
          z_rot     --- rotation angle about the z-axis (coalescence angle)
          psi_rot   --- overall phase adjustment of exp(1.0j*psi_rot) mixing h+,hx
          """

      if times.min() < t_min or times.max() > t_max:
        raise ValueError('surrogate cannot be evaluated outside of its time window')

      if psi_rot is not None:
        raise ValueError('not coded yet')

      ### output will be h (if theta,phi specified) or hp_modes, hc_modes ###
      if theta is not None and phi is not None:
        h = np.zeros((times.shape[0],),dtype=complex)
      else:
        hp_modes, hc_modes = self._allocate_output_array(times,len(modes_to_evaluate))

      ### evaluate modes at times ###
      jj=0
      for ell_m in modes_to_evaluate:
        hp_modes_eval = splev(times, hp_modes_spline[ell_m])
        hc_modes_eval = splev(times, hc_modes_spline[ell_m])

        ### apply rotation about z axis and evaluation on sphere if requested ###
        h_modes_eval  = hp_modes_eval + 1.0j*hc_modes_eval
        if z_rot is not None:
          h_modes_eval = h_modes_eval*np.exp(1.0j*z_rot*ell_m[1])
        
        if theta is not None and phi is not None:
          sYlm_value =  sYlm(-2,ll=ell_m[0],mm=ell_m[1],theta=theta,phi=phi)
          h = h + sYlm_value*h_modes_eval
        else:
          hp_modes[:,jj] = h_modes_eval.real
          hc_modes[:,jj] = h_modes_eval.imag
          jj+=1

      if theta is not None and phi is not None:
        return h.real, h.imag
      else:
        return hp_modes, hc_modes
    
    return h_sphere, modes_to_evaluate, [t_min, t_max]


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def evaluate_on_sphere(self,ell,m,theta,phi,hp_mode,hc_mode):
    """evaluate on the sphere"""

    if theta is not None: 
      if phi is None: phi = 0.0
      sYlm_value =  sYlm(-2,ll=ell,mm=m,theta=theta,phi=phi)
      h = sYlm_value*(hp_mode + 1.0j*hc_mode)
      hp_mode = h.real
      hc_mode = h.imag

    return hp_mode, hc_mode

  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def evaluate_single_mode(self,q, M, dist, phi_ref, f_low, samples, samples_units,ell,m):
    """ light wrapper around single mode evaluator to gaurd against m < 0 modes """

    if m >=0:
      #mode_key = 'l'+str(ell)+'_m'+str(m)
      mode_key = (ell,m)
      t_mode, hp_mode, hc_mode = self.single_modes[mode_key](q, M, dist, phi_ref, f_low, samples, samples_units)
    else:
      raise ValueError('m must be non-negative. evalutate m < 0 modes with evaluate_single_mode_minus')

    return t_mode, hp_mode, hc_mode


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def evaluate_single_mode_minus(self,q, M, dist, phi_ref, f_low, samples,samples_units,ell,m):
    """ evaluate m<0 mode from m>0 mode and relationship between these"""

    if m<0:
      t_mode, hp_mode, hc_mode = self.evaluate_single_mode(q, M, dist, phi_ref, f_low, samples,samples_units,ell,-m)
      hp_mode, hc_mode         = self._generate_minus_m_mode(hp_mode,hc_mode,ell,-m)
    else:
      raise ValueError('m must be negative.')

    return t_mode, hp_mode, hc_mode


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def generate_mode_eval_list(self,ell=None,m=None,minus_m=False):
    """generate list of (ell,m) modes to evaluate for.

      1) ell=m=None: use all available model modes
      2) ell=NUM, m=None: all modes up to ell_max = NUM. unmodelled modes set to zero
      3) list of [ell], [m] pairs: only use modes (ell,m). unmodelled modes set to zero 

      These three options produce a list of (ell,m) modes. set minus_m=True 
      to generate m<0 modes from m>0 modes."""

    ### generate list of nonnegative m modes to evaluate for ###
    if ell is None and m is None:
      modes_to_eval = self.all_model_modes()
    elif m is None:
      LMax = ell
      modes_to_eval = []
      for L in range(2,LMax+1):
        for emm in range(0,L+1):
          modes_to_eval.append((L,emm))
    else:
      modes_to_eval = [(x, y) for x in ell for y in m]

    ### if m<0 requested, build these from m>=0 list ###
    if minus_m:
      modes_to_eval = self._extend_mode_list_minus_m(modes_to_eval)

    return modes_to_eval

  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def sort_mode_list(self,mode_list):
    """sort modes as (2,-2), (2,-1), ..., (2,2), (3,-3),(3,-2)..."""

    from operator import itemgetter

    mode_list = sorted(mode_list, key=itemgetter(0,1))
    return mode_list


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def all_model_modes(self,minus_m=False):
    """ from single mode keys deduce all available model modes.
        If minus_m=True, include (ell,-m) whenever (ell,m) is available ."""

    #model_modes = [(int(tmp[1]),int(tmp[4])) for tmp in self.single_modes.keys()]
    model_modes = [(ell,m) for ell,m in self.single_modes.keys()]

    if minus_m:
      model_modes = self._extend_mode_list_minus_m(model_modes)

    return model_modes


  #### below here are "private" member functions ###
  # These routine's carry out inner workings of multimode surrogate
  # class (such as memory allocation)
 
  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def _allocate_output_array(self,samples,num_modes):
    """ allocate memory for result of hp, hc.

    Input
    =====
    samples   --- array of time samples. None if using default
    num_modes --- number of harmonic modes (cols). set to 1 if summation over modes"""

    if (samples is not None):
      hp_full = np.zeros((samples.shape[0],num_modes))
      hc_full = np.zeros((samples.shape[0],num_modes))
    else:
      hp_full = np.zeros((self.time_all_modes().shape[0],num_modes))
      hc_full = np.zeros((self.time_all_modes().shape[0],num_modes))

    if( num_modes == 1): #TODO: hack to prevent broadcast when summing over modes
      hp_full = hp_full.reshape([hp_full.shape[0],])
      hc_full = hp_full.reshape([hp_full.shape[0],])

    return hp_full, hc_full


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def _generate_minus_m_mode(self,hp_mode,hc_mode,ell,m):
    """ For m>0 positive modes hp_mode,hc_mode use h(l,-m) = (-1)^l h(l,m)^*
        to compute the m<0 mode. 

  See Kidder,Physical Review D 77, 044016 (2008), arXiv:0710.0614v1 [gr-qc]."""

    if (m<=0):
      raise ValueError('m must be nonnegative. m<0 will be generated for you from the m>0 mode.')
    else:
      hp_mode =   np.power(-1,ell) * hp_mode
      hc_mode = - np.power(-1,ell) * hc_mode

    return hp_mode, hc_mode


  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  def _extend_mode_list_minus_m(self,mode_list):
    """ from list of [(ell,m)] pairs return a new list which includes m<0 too."""

    positive_modes = list(mode_list)
    for ell,m in positive_modes:
      if m>0:
        mode_list.append((ell,-m))
      if m<0:
        raise ValueError('your list already has negative modes!')

    return mode_list


####################################################
def CompareSingleModeSurrogate(sur1,sur2):
  """ Compare data defining two surrogates"""

  #TODO: should loop over necessary and optional data fields in future SurrogateIO class

  for key in sur1.__dict__.keys():

    if key in ['B','V','R','fitparams_phase','fitparams_amp',\
               'fitparams_norm','greedy_points','eim_indices']:

      if np.max(np.abs(sur1.__dict__[key] - sur2.__dict__[key])) != 0:
        print "checking attribute "+str(key)+"...DIFFERENT!!!"
      else:
        print "checking attribute "+str(key)+"...agrees"

    elif key in ['fit_type_phase','fit_type_amp','fit_type_norm']:

      if sur1.__dict__[key] == sur2.__dict__[key]:
        print "checking attribute "+str(key)+"...agrees"
      else:
         print "checking attribute "+str(key)+"...DIFFERENT!!!"

    else:
      print "not checking attribute "+str(key)



