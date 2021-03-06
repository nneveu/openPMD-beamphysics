from .units import dimension, dimension_name, SI_symbol, pg_units
from .interfaces.astra import write_astra
from .interfaces.opal import write_opal
from .readers import particle_array
from .writers import write_pmd_bunch, pmd_init

from h5py import File
import numpy as np
import scipy.constants



mass_of = {'electron': 0.51099895000e6 # eV/c
              }
c_light = 299792458.
e_charge = scipy.constants.e
charge_of = {'electron': e_charge, 'positron':-e_charge}
charge_state = {'electron': -1}


#-----------------------------------------
# Classes


class ParticleGroup:
    """
    Particle Group class
    
    Initialized on on openPMD beamphysics particle group:
        h5 = open h5 handle, or str that is a file
        data = raw data
    
    The fundamental bunch data is stored in __dict__ with keys
        np.array: x, px, y, py, z, pz, t, status, weight
        str: species
    where:
        x, y, z are positions in units of [m]
        px, py, pz are momenta in units of [eV/c]
        t is time in [s]
        weight is the macro-charge weight in [C], used for all statistical calulations.
        species is a proper species name: 'electron', etc. 
        
    Derived data can be computed as attributes:
        .gamma, .beta, .beta_x, .beta_y, .beta_z: relativistic factors [1].
        .r, .theta: cylidrical coordinates [m], [1]
        .pr, .ptheta: cylindrical momenta [1]
        .energy : total energy [eV]
        .kinetic_energy: total energy - mc^2 in [eV]. 
        .p: total momentum in [eV/c]
        .mass: rest mass in [eV]
        .xp, .yp: Slopes x' = dx/dz = dpx/dpz and y' = dy/dz = dpy/dpz [1].
        
    Statistics of any of these are calculated with:
        .min(X)
        .max(X)
        .ptp(X)
        .avg(X)
        .std(X)
        .cov(X, Y, ...)
        with a string X as the name any of the properties above.
        
    Useful beam physics quantities are given as attributes:
        .norm_emit_x
        .norm_emit_y
        .higher_order_energy_spread
        .average_current
            
    All attributes can be accessed with brackets:
        [key]
    Additional keys are allowed for convenience:
        ['min_prop']   will return  .min('prop')
        ['max_prop']   will return  .max('prop')
        ['ptp_prop']   will return  .ptp('prop')
        ['mean_prop']  will return  .avg('prop')
        ['sigma_prop'] will return  .std('prop')
        ['cov_prop1__prop2'] will return .cov('prop1', 'prop2')[0,1]
        
    Units for all attributes can be accessed by:
        .units(key)
    
    Particles are often stored at the same time (i.e. from a t-based code), 
    or with the same z position (i.e. from an s-based code.)
    Routines: 
        drift_to_z(z0)
        drift_to_t(t0)
    help to convert these. If no argument is given, particles will be drifted to the mean.
        
    
    """
    def __init__(self, h5=None, data=None):
    
        if h5:
            # Allow filename
            if isinstance(h5, str) and os.path.exists(h5):
                with File(h5, 'r') as hh5:
                    pp = particle_paths(hh5)
                    assert len(pp) == 1, f'Number of particle paths in {h5}: {len(pp)}'
                    data = load_bunch_data(hh5[pp[0]])

            else:
                # Try dict
                data = load_bunch_data(h5)
        else:
            # Fill out data. Exclude species.
            data = full_data(data)
            species = list(set(data['species']))
            
            # Allow for empty data (len=0). Otherwise, check species.
            if len(species) >= 1:
                assert len(species) == 1, f'mixed species are not allowed: {species}'
                data['species'] = species[0]
            
            
        self._settable_array_keys = ['x', 'px', 'y', 'py', 'z', 'pz', 't', 'status', 'weight']
        self._settable_scalar_keys = ['species']
        self._settable_keys =  self._settable_array_keys + self._settable_scalar_keys                       
        for key in self._settable_keys:
            self.__dict__[key] = data[key]
    
    
    @property
    def n_particle(self):
        """Total number of particles. Same as len """
        return len(self)
    
    @property
    def n_alive(self):
        """Number of alive particles, defined by status == 1"""
        return len(np.where(self.status==1)[0])
    
    @property
    def n_dead(self):
        """Number of alive particles, defined by status != 1"""
        return self.n_particle - self.n_alive
    
        
    def units(self, key):
        """Returns the units of any key"""
        return pg_units(key)
        
    @property
    def mass(self):
        """Rest mass in eV"""
        return mass_of[self.species]

    @property
    def species_charge(self):
        """Species charge in C"""
        return charge_of[self.species]
    
    @property
    def charge(self):
        return np.sum(self.weight)
    
    # Relativistic properties
    @property
    def p(self):
        """Total momemtum in eV/c"""
        return np.sqrt(self.px**2 + self.py**2 + self.pz**2) 
    @property
    def energy(self):
        """Total energy in eV"""
        return np.sqrt(self.px**2 + self.py**2 + self.pz**2 + self.mass**2) 
    @property
    def kinetic_energy(self):
        """Kinetic energy in eV"""
        return self.energy - self.mass
    
    # Slopes. Note that these are relative to pz
    @property
    def xp(self):
        return self.px/self.pz  
    @property
    def yp(self):
        return self.py/self.pz    
    
    # Cylindrical coordinates. Note that these are ali
    @property
    def r(self):
        return np.hypot(self.x, self.y)
    @property    
    def theta(self):
        return np.arctan2(self.y, self.x)
    @property
    def pr(self):
        return np.hypot(self.px, self.py)
    @property    
    def ptheta(self):
        return np.arctan2(self.py, self.px)    
    
    
    # Relativistic quantities
    @property
    def gamma(self):
        """Relativistic gamma"""
        return self.energy/self.mass
    @property
    def beta(self):
        """Relativistic beta"""
        return self.p/self.energy
    @property
    def beta_x(self):
        """Relativistic beta, x component"""
        return self.px/self.energy
    @property
    def beta_y(self):
        """Relativistic beta, y component"""
        return self.py/self.energy
    @property
    def beta_z(self):
        """Relativistic beta, z component"""
        return self.pz/self.energy
    
    
    
    def delta(self, key):
        """Attribute (array) relative to its mean"""
        return getattr(self, key) - self.avg(key)
    
    
    # Statistical property functions
    
    def min(self, key):
        """Minimum of any key"""
        return np.min(getattr(self, key))
    def max(self, key):
        """Maximum of any key"""
        return np.max(getattr(self, key)) 
    def ptp(self, key):
        """Peak-to-Peak = max - min of any key"""
        return np.ptp(getattr(self, key))     
        
    def avg(self, key):
        """Statistical average"""
        dat = getattr(self, key) # equivalent to self.key for accessing properties above
        if np.isscalar(dat): 
            return dat
        return np.average(dat, weights=self.weight)
    def std(self, key):
        """Standard deviation (actually sample)"""
        dat = getattr(self, key)
        if np.isscalar(dat):
            return 0
        avg_dat = self.avg(key)
        return np.sqrt(np.average( (dat - avg_dat)**2, weights=self.weight))
    def cov(self, *keys):
        """
        Covariance matrix from any properties
    
        Example: 
        P = ParticleGroup(h5)
        P.cov('x', 'px', 'y', 'py')
    
        """
        dats = np.array([ getattr(self, key) for key in keys ])
        return np.cov(dats, aweights=self.weight)
    
    # Beam statistics
    @property
    def norm_emit_x(self):
        """Normalized emittance in the x plane"""
        mat = self.cov('x', 'px')
        return  np.sqrt(mat[0,0]*mat[1,1]-mat[0,1]**2)/self.mass
    @property
    def norm_emit_y(self):       
        mat = self.cov('y', 'py')
        """Normalized emittance in the y plane"""
        return  np.sqrt(mat[0,0]*mat[1,1]-mat[0,1]**2)/self.mass
    @property
    def higher_order_energy_spread(self, order=2):
        """
        Fits a quadratic (order=2) to the Energy vs. time, subtracts it, finds the rms of the residual in eV.
        
        If all particles are at the same
        """
        
        if self.std('z') < 1e-12:
            # must be at a screen. Use t
            t = self.t
        else:
            # All particles at the same time. Use z to calc t
            t = self.z/c_light
        energy = self.energy
        
        best_fit_coeffs = np.polynomial.polynomial.polyfit(t, energy, order)
        best_fit = np.polynomial.polynomial.polyval(t, best_fit_coeffs)
        return np.std(energy - best_fit)        
    @property
    def average_current(self):
        """
        Simple average current in A: charge / dt, with dt =  (max_t - min_t)
        If particles are in t coordinates, will try dt = (max_z - min_z)*c_light*beta_z
        """
        dt = self.t.ptp()  # ptp 'peak to peak' is max - min
        if dt == 0:
            # must be in t coordinates. Calc with 
            dt = self.z.ptp() / (self.avg('beta_z')*c_light)
        return self.charge / dt
    
    def __getitem__(self, key):
        """
        Returns a property or statistical quantity that can be computed:
        P['x'] returns the x array
        P['sigmx_x'] returns the std(x) scalar
        P['norm_emit_x'] returns the norm_emit_x scalar
        
        Parts can also be given. Example: P[0:10] returns a new ParticleGroup with the first 10 elements.
        """
        
        # Allow for non-string operations: 
        if not isinstance(key, str):
            return particle_parts(self, key)
    
        if key.startswith('cov_'):
            subkeys = key[4:].split('__')
            assert len(subkeys) == 2, f'Too many properties in covariance request: {key}'
            return self.cov(*subkeys)[0,1]
        elif key.startswith('delta_'):
            return self.delta(key[6:])
        elif key.startswith('sigma_'):
            return self.std(key[6:])
        elif key.startswith('mean_'):
            return self.avg(key[5:])
        elif key.startswith('min_'):
            return self.min(key[4:])
        elif key.startswith('max_'):
            return self.max(key[4:])     
        elif key.startswith('ptp_'):
            return self.ptp(key[4:])         
        
        else:
            return getattr(self, key) 
    
    def where(self, x):
        return self[np.where(x)]
    
    # TODO: should the user be allowed to do this?
    #def __setitem__(self, key, value):    
    #    assert key in self._settable_keyes, 'Error: you cannot set:'+str(key)
    #    
    #    if key in self._settable_array_keys:
    #        assert len(value) == self.n_particle
    #        self.__dict__[key] = value
    #    elif key == 
    #        print()
     
    # Simple 'tracking'     
    def drift(self, delta_t):
        """
        Drifts particles by time delta_t
        """
        self.x = self.x + self.beta_x * c_light * delta_t
        self.y = self.y + self.beta_y * c_light * delta_t
        self.z = self.z + self.beta_z * c_light * delta_t
        self.t = self.t + delta_t
    
    def drift_to_z(self, z=None):

        if not z:
            z = self.avg('z')
        dt = (z - self.z) / (self.beta_z * c_light)
        self.drift(dt)
        # Fix z to be exactly this value
        self.z = np.full(self.n_particle, z)
        
        
    def drift_to_t(self, t=None):
        """
        Drifts all particles to the same t
        
        If no z is given, particles will be drifted to the average t
        """
        if not t:
            t = self.avg('t')
        dt = t - self.t
        self.drift(dt)
        # Fix t to be exactly this value
        self.t = np.full(self.n_particle, t)
    
    # Writers
    def write_astra(self, filePath, verbose=False):
        write_astra(self, filePath, verbose=verbose)
    def write_opal(self, filePath, verbose=False):
        write_opal(self, filePath, verbose=verbose)
        
    # openPMD    
    def write(self, h5, name=None):
        """
        Writes to an open h5 handle, or new file if h5 is a str.
        
        """
        if isinstance(h5, str):
            g = File(h5, 'w')
            pmd_init(g, basePath='/', particlesPath='/' )
        else:
            g = h5
    
        write_pmd_bunch(g, self, name=name)        
        
    # New constructors
    def split(self, n_chunks = 100, key='z'):
        return split_particles(self, n_chunks=n_chunks, key=key)
    
    # Resample
    def resample(self, n):
        """
        Resamples n particles.
        """
        return resample(self, n)
    
    # Internal sorting
    def _sort(self, key):
        """Sorts internal arrays by key"""
        ixlist = np.argsort(self[key])
        for k in self._settable_array_keys:
            self.__dict__[k] = self[k][ixlist]    
        
    # Operator overloading    
    def __add__(self, other):
        """
        Overloads the + operator to join particle groups.
        Simply calls join_particle_groups
        """
        return join_particle_groups(self, other)
    
    
    def __len__(self):
        return len(self[self._settable_array_keys[0]])
    
    def __str__(self):
        s = f'ParticleGroup with {self.n_particle} particles with total charge {self.charge} C'
        return s

    def __repr__(self):
        memloc = hex(id(self))
        return f'<ParticleGroup with {self.n_particle} particles at {memloc}>'
            
            
    




    


#-----------------------------------------
# helper funcion for ParticleGroup class
    
    
def load_bunch_data(h5):
    """
    Load particles into structured numpy array.
    """
    n = len(h5['position/x'])
    
    attrs = dict(h5.attrs)
    data = {}
    data['species'] = attrs['speciesType'].decode('utf-8') # String
    n_particle = int(attrs['numParticles'])
    data['total_charge'] = attrs['totalCharge']*attrs['chargeUnitSI']
    
    for key in ['x', 'px', 'y', 'py', 'z', 'pz', 't']:
        data[key] = particle_array(h5, key)
        
    if 'particleStatus' in h5:
        data['status'] = particle_array(h5, 'particleStatus')
    else:
        data['status'] = np.full(n_particle, 1)
    
    # Make sure weight is populated
    if 'weight' in h5:
        weight = particle_array(h5, 'weight')
        if len(weight) == 1:
            weight = np.full(n_particle, weight[0])
    else:
        weight = np.full(n_particle, data['total_charge']/n_particle)
    data['weight'] = weight
        
    return data



def full_data(data, exclude=None):
    """
    Expands keyed data into np arrays, assuring that the lengths of all items are the same. 
    
    Allows for some keys to be scalars or length 1, and fills them out with np.full.
    
    
    """
    
    full_data = {}
    scalars = {}
    for k, v in data.items():
        if np.isscalar(v):
            scalars[k] = v
        elif len(v) == 1:
            scalars[k] = v[0]
        else:
            # must be array
            full_data[k] = np.array(v)
    
    # Check for single particle
    if len(full_data) == 0:
        return {k:np.array([v]) for k, v in scalars.items()}
            
    # Array data should all have the same length
    nlist = [len(v) for _, v in full_data.items()]
    assert len(set(nlist)) == 1, f'arrays must have the same length. Found len: { {k:len(v) for k, v in full_data.items()} }'
    
    for k, v in scalars.items():
        full_data[k] = np.full(nlist[0], v)
    
    return full_data


def split_particles(particle_group, n_chunks = 100, key='z'):
    """
    Splits a particle group into even chunks. Returns a list of particle groups. 
    
    Useful for creating slice statistics. 
    
    """
    
    # Sorting
    zlist = getattr(particle_group, key) 
    iz = np.argsort(zlist)

    # Split particles into chunks
    plist = []
    for chunk in np.array_split(iz, n_chunks):
        # Prepare data
        data = {}
        #keys = ['x', 'px', 'y', 'py', 'z', 'pz', 't', 'status', 'weight'] 
        for k in particle_group._settable_array_keys:
            data[k] = getattr(particle_group, k)[chunk]
        # These should be scalars
        data['species'] = particle_group.species
        
        # New object
        p = ParticleGroup(data=data)
        plist.append(p)
        
    return plist

def resample(particle_group, n):
    """
    Resamples a ParticleGroup randomly.
    
    Returns a new ParticleGroup instance.
    
    Note that this only works if the weights are the same
    
    """
    n_old = particle_group.n_particle
    assert n <= n_old, 'Cannot supersample'
    assert len(set(particle_group.weight)) == 1, 'non-unique weights for resampling.'
    ixlist = np.random.choice(n_old, n, replace=False)
    data = {}
    for key in particle_group._settable_array_keys:
        data[key] = particle_group[key][ixlist]
    data['species'] = particle_group['species']
    data['weight'] *= n_old/n # Need to re-weight
    
    return ParticleGroup(data=data)



def particle_parts(particle_group, x):
    """
    Gets parts of a ParticleGroup object. Returns a new ParticleGroup
    """
    data = {}
    for k in particle_group._settable_array_keys:
        data[k] = particle_group[k][x]

    for k in particle_group._settable_scalar_keys:
        data[k] = particle_group[k]

    return ParticleGroup(data=data)
           
    
    


    
def join_particle_groups(*particle_groups):
    """
    Join particle groups. 
    
    This simply concatenates the internal particle arrays.
    
    Species must be the same
    """
    species = [pg['species'] for pg in particle_groups]
    #return species 

    species0 = species[0]
    assert all([spe == species0 for spe in species]) , 'species must be the same to join'
    
    data = {}
    for key in particle_groups[0]._settable_array_keys:
        data[key] = np.hstack([pg[key] for pg in particle_groups ])
    
    data['species'] = species0
    data['n_particle'] = np.sum( [pg['n_particle'] for pg in particle_groups]) 
    
    return ParticleGroup(data=data)    
    
    
    
def slice_statistics(particle_group,  keys=['mean_z'], n_slice=40, slice_key='z'):
    """
    Slices a particle group into n slices and returns statistics from each sliced defined in keys. 
    
    These statistics should be scalar floats for now.
    
    Any key can be used to slice on. 
    
    """
    sdat = {}
    for k in keys:
        sdat[k] = np.empty(n_slice)
    for i, pg in enumerate(particle_group.split(n_slice, key=slice_key)):
        for k in keys:
            sdat[k][i] = pg[k]
            
    return sdat
    


        




