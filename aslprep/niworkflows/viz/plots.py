# -*- coding: utf-8 -*-
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""Plotting tools shared across MRIQC and FMRIPREP"""

import numpy as np
import nibabel as nb
import pandas as pd

import matplotlib.pyplot as plt
from matplotlib import gridspec as mgs
import matplotlib.cm as cm
from matplotlib.colors import ListedColormap, Normalize
from matplotlib.colorbar import ColorbarBase

from nilearn.plotting import plot_img
from nilearn.signal import clean
from nilearn._utils import check_niimg_4d
from nilearn._utils.niimg import _safe_get_data
from svgutils.transform import SVGFigure
from nilearn.plotting import plot_stat_map
from lxml import etree
from .. import NIWORKFLOWS_LOG
import seaborn as sns
from seaborn import color_palette
from .utils import extract_svg,robust_set_limits

DINA4_LANDSCAPE = (11.69, 8.27)


class fMRIPlot(object):
    """
    Generates the fMRI Summary Plot
    """
    __slots__ = ['func_file', 'mask_data',
                 'tr', 'seg_data', 'confounds', 'spikes']

    def __init__(self, func_file, mask_file=None, data=None, conf_file=None, seg_file=None,
                 tr=None, usecols=None, units=None, vlines=None, spikes_files=None):
        self.func_file = func_file
        func_nii = nb.load(func_file)
        self.tr = tr if tr is not None else func_nii.header.get_zooms()[-1]

        self.mask_data = nb.fileslice.strided_scalar(func_nii.shape[:3], np.uint8(1))
        if mask_file:
            self.mask_data = np.asanyarray(nb.load(mask_file).dataobj).astype('uint8')

        self.seg_data = None
        if seg_file:
            self.seg_data = np.asanyarray(nb.load(seg_file).dataobj)

        if units is None:
            units = {}

        if vlines is None:
            vlines = {}

        self.confounds = {}
        if data is None and conf_file:
            data = pd.read_csv(conf_file, sep=r'[\t\s]+',
                               usecols=usecols, index_col=False)

        if data is not None:
            for name in data.columns.ravel():
                self.confounds[name] = {
                    'values': data[[name]].values.ravel().tolist(),
                    'units': units.get(name),
                    'cutoff': vlines.get(name)
                }

        self.spikes = []
        if spikes_files:
            for sp_file in spikes_files:
                self.spikes.append((np.loadtxt(sp_file), None, False))

    def plot(self, figure=None):
        """Main plotter"""
        sns.set_style("whitegrid")
        sns.set_context("paper", font_scale=0.8)

        if figure is None:
            figure = plt.gcf()

        nconfounds = len(self.confounds)
        nspikes = len(self.spikes)
        nrows = 1 + nconfounds + nspikes

        # Create grid
        grid = mgs.GridSpec(nrows, 1, wspace=0.0, hspace=0.05,
                            height_ratios=[1] * (nrows - 1) + [5])

        grid_id = 0
        for tsz, name, iszs in self.spikes:
            spikesplot(tsz, title=name, outer_gs=grid[grid_id], tr=self.tr,
                       zscored=iszs)
            grid_id += 1

        if self.confounds:
            palette = color_palette("husl", nconfounds)

        for i, (name, kwargs) in enumerate(self.confounds.items()):
            tseries = kwargs.pop('values')
            confoundplot(
                tseries, grid[grid_id], tr=self.tr, color=palette[i],
                name=name, **kwargs)
            grid_id += 1

        plot_carpet(self.func_file, self.seg_data, subplot=grid[-1], tr=self.tr)
        # spikesplot_cb([0.7, 0.78, 0.2, 0.008])
        return figure


class CBFtsPlot(object):
    """
    Generates the CBF Summary Plot
    """
    __slots__ = ['cbf_file','tr', 'seg_data', 'fd_file']

    def __init__(self,cbf_file,qc_file=None, seg_file=None,scoreindex=None,
                 tr=None, usecols=None, units=None, vlines=None):
        from nilearn.image import (load_img)
        if scoreindex:
            cbfts = load_img(cbf_file).get_fdata()
            volindex = np.loadtxt(scoreindex)
            cbfts[..., (volindex != 0)] = np.nan
            cbfts1 = load_img(cbf_file)
            img_in = nb.Nifti1Image(dataobj=cbfts, affine=cbfts1.affine, header=cbfts1.header)
            self.cbf_file=img_in
        else:
            self.cbf_file=cbf_file
        
        func_nii = nb.load(cbf_file)
        self.tr = tr if tr is not None else func_nii.header.get_zooms()[-1]

        self.seg_data = None
        if seg_file:
            self.seg_data = np.asanyarray(nb.load(seg_file).dataobj)

        if units is None:
            units = {}

        if vlines is None:
            vlines = {}

        self.fd_file = {}
        if qc_file:
            data = pd.read_csv(qc_file, sep='\t')
            fdlist=data['framewise_displacement'].tolist()
            fdlist=fdlist[::2]
            fdlist=np.nan_to_num(fdlist)
            self.fd_file['FD'] = {
                    'values':fdlist,
                    'units': '',
                    'cutoff': ''
                }
        if scoreindex:
            self.fd_file['Score Index'] = {
                    'values': volindex,
                    'units': '',
                    'cutoff': ''}

    def plot(self, figure=None):
        """Main plotter"""
        sns.set_style("whitegrid")
        sns.set_context("paper", font_scale=0.8)

        if figure is None:
            figure = plt.gcf()

        nconfounds = len(self.fd_file)
        nrows = 1 + nconfounds

        # Create grid
        grid = mgs.GridSpec(nrows, 1, wspace=0.0, hspace=0.05,
                            height_ratios=[1] * (nrows - 1) + [5])

        grid_id = 0

        if self.fd_file:
            palette = color_palette("husl", nconfounds)

        for i, (name, kwargs) in enumerate(self.fd_file.items()):
            tseries = kwargs.pop('values')
            confoundplot(
                tseries, grid[grid_id], tr=self.tr, color=palette[i],
                name=name, **kwargs)
            grid_id += 1

        plot_carpet(self.cbf_file, self.seg_data, subplot=grid[-1], tr=self.tr)
        # spikesplot_cb([0.7, 0.78, 0.2, 0.008])
        return figure



class CBFPlot(object):
    """
    Generates the cbf Summary Plot
    """
    __slots__ = ['cbf','ref_vol']

    def __init__(self,cbf,ref_vol):
        self.cbf = cbf
        self.score = score
        self.scrub = scrub
        self.basil=basil
        self.pvc=pvc
        self.ref_vol=ref_vol

    def plot(self, figure=None):
        """Main plotter"""
        cbfmaps=[self.cbf,self.score,self.scrub,self.basil,self.pvc]
        #cbfmapsnames=['cbf','score_cbf','scrub_cbf','basil_cbf','pvc_cbf']
        import matplotlib.pyplot as plt
        from matplotlib import gridspec as mgs
        from nilearn.plotting import plot_stat_map 
        
        ax=plt.gcf()
       
        grid = mgs.GridSpec(5, 1)

        plotstatsimg(cbfmaps[0],ref_vol=self.ref_vol,subplot=grid[0], output_file=None)
        plotstatsimg(cbfmaps[1],ref_vol=self.ref_vol,subplot=grid[1], output_file=None)
        plotstatsimg(cbfmaps[2],ref_vol=self.ref_vol,subplot=grid[2], output_file=None)
        plotstatsimg(cbfmaps[3],ref_vol=self.ref_vol,subplot=grid[3], output_file=None)
        plotstatsimg(cbfmaps[4],ref_vol=self.ref_vol,subplot=grid[4], output_file=None)
     
        return ax



def plotstatsimg(cbf,ref_vol,div_id,plot_params=None,order=('z', 'x', 'y'), cuts=None,
                      estimate_brightness=False, label=None,compress='auto'):
    """
    plot zsts
    """
    plot_params = {} if plot_params is None else plot_params

    # Use default MNI cuts if none defined
    if cuts is None:
        raise NotImplementedError  # TODO

    out_files = []
    if estimate_brightness:
        plot_params = robust_set_limits(cbf.get_fdata().reshape(-1),
                                        plot_params)

    # Plot each cut axis
    for i, mode in enumerate(list(order)):
        plot_params['display_mode'] = mode
        plot_params['cut_coords'] = cuts[mode]
        plot_params['draw_cross']=False
        plot_params['symmetric_cbar']=True
        plot_params['threshold']=0
        plot_params['vmax']=90
        if i == 0:
            plot_params['title'] = label
            plot_params['colorbar']= True
        else:
            plot_params['title'] = None

        # Generate nilearn figure
        display = plot_stat_map(tat_map_img=cbf,bg_img=ref_vol, **plot_params)
        svg = extract_svg(display, compress=compress)
        display.close()

        # Find and replace the figure_1 id.
        try:
            xml_data = etree.fromstring(svg)
        except etree.XMLSyntaxError as e:
            NIWORKFLOWS_LOG.info(e)
            return

        svg_fig = SVGFigure()
        svg_fig.root = xml_data
        out_files.append(svg_fig)

    return out_files


def plot_carpet(img, atlaslabels, detrend=True, nskip=0, size=(950, 800),
                subplot=None, title=None, output_file=None, legend=False,
                lut=None, tr=None):
    """
    Plot an image representation of voxel intensities across time also know
    as the "carpet plot" or "Power plot". See Jonathan Power Neuroimage
    2017 Jul 1; 154:150-158.

    Parameters
    ----------

        img : Niimg-like object
            See http://nilearn.github.io/manipulating_images/input_output.html
            4D input image
        atlaslabels: ndarray
            A 3D array of integer labels from an atlas, resampled into ``img`` space.
        detrend : boolean, optional
            Detrend and standardize the data prior to plotting.
        nskip : int
            Number of volumes at the beginning of the scan marked as nonsteady state.
        long_cutoff : int
            Number of TRs to consider img too long (and decimate the time direction
            to save memory)
        axes : matplotlib axes, optional
            The axes used to display the plot. If None, the complete
            figure is used.
        title : string, optional
            The title displayed on the figure.
        output_file : string, or None, optional
            The name of an image file to export the plot to. Valid extensions
            are .png, .pdf, .svg. If output_file is not None, the plot
            is saved to a file, and the display is closed.
        legend : bool
            Whether to render the average functional series with ``atlaslabels`` as
            overlay.
        tr : float , optional
            Specify the TR, if specified it uses this value. If left as None,
            # Frames is plotted instead of time.
    """

    # Define TR and number of frames
    notr = False
    if tr is None:
        notr = True
        tr = 1.

    img_nii = check_niimg_4d(img, dtype='auto',)
    func_data = _safe_get_data(img_nii, ensure_finite=True)
    ntsteps = func_data.shape[-1]

    data = func_data[atlaslabels > 0].reshape(-1, ntsteps)
    seg = atlaslabels[atlaslabels > 0].reshape(-1)

    # Map segmentation
    if lut is None:
        lut = np.zeros((256, ), dtype='int')
        lut[1:11] = 1
        lut[255] = 2
        lut[30:99] = 3
        lut[100:201] = 4

    # Apply lookup table
    newsegm = lut[seg.astype(int)]

    p_dec = 1 + data.shape[0] // size[0]
    if p_dec:
        data = data[::p_dec, :]
        newsegm = newsegm[::p_dec]

    t_dec = 1 + data.shape[1] // size[1]
    if t_dec:
        data = data[:, ::t_dec]

    # Detrend data
    v = (None, None)
    if detrend:
        data = clean(data.T, t_r=tr).T
        v = (-2, 2)

    # Order following segmentation labels
    order = np.argsort(newsegm)[::-1]

    # If subplot is not defined
    if subplot is None:
        subplot = mgs.GridSpec(1, 1)[0]

    # Define nested GridSpec
    wratios = [1, 100, 20]
    gs = mgs.GridSpecFromSubplotSpec(1, 2 + int(legend), subplot_spec=subplot,
                                     width_ratios=wratios[:2 + int(legend)],
                                     wspace=0.0)

    mycolors = ListedColormap(cm.get_cmap('tab10').colors[:4][::-1])

    # Segmentation colorbar
    ax0 = plt.subplot(gs[0])
    ax0.set_yticks([])
    ax0.set_xticks([])
    ax0.imshow(newsegm[order, np.newaxis], interpolation='none', aspect='auto',
               cmap=mycolors, vmin=1, vmax=4)
    ax0.grid(False)
    ax0.spines["left"].set_visible(False)
    ax0.spines["bottom"].set_color('none')
    ax0.spines["bottom"].set_visible(False)

    # Carpet plot
    ax1 = plt.subplot(gs[1])
    ax1.imshow(data[order, ...], interpolation='nearest', aspect='auto', cmap='gray',
               vmin=v[0], vmax=v[1])

    ax1.grid(False)
    ax1.set_yticks([])
    ax1.set_yticklabels([])

    # Set 10 frame markers in X axis
    interval = max((int(data.shape[-1] + 1) // 10, int(data.shape[-1] + 1) // 5, 1))
    xticks = list(range(0, data.shape[-1])[::interval])
    ax1.set_xticks(xticks)
    if notr:
        ax1.set_xlabel('time (frame #)')
    else:
        ax1.set_xlabel('time (s)')
    labels = tr * (np.array(xticks)) * t_dec
    ax1.set_xticklabels(['%.02f' % t for t in labels.tolist()], fontsize=5)

    # Remove and redefine spines
    for side in ["top", "right"]:
        # Toggle the spine objects
        ax0.spines[side].set_color('none')
        ax0.spines[side].set_visible(False)
        ax1.spines[side].set_color('none')
        ax1.spines[side].set_visible(False)

    ax1.yaxis.set_ticks_position('left')
    ax1.xaxis.set_ticks_position('bottom')
    ax1.spines["bottom"].set_visible(False)
    ax1.spines["left"].set_color('none')
    ax1.spines["left"].set_visible(False)

    if legend:
        gslegend = mgs.GridSpecFromSubplotSpec(
            5, 1, subplot_spec=gs[2], wspace=0.0, hspace=0.0)
        epiavg = func_data.mean(3)
        epinii = nb.Nifti1Image(epiavg, img_nii.affine, img_nii.header)
        segnii = nb.Nifti1Image(lut[atlaslabels.astype(int)], epinii.affine, epinii.header)
        segnii.set_data_dtype('uint8')

        nslices = epiavg.shape[-1]
        coords = np.linspace(int(0.10 * nslices), int(0.95 * nslices), 5).astype(np.uint8)
        for i, c in enumerate(coords.tolist()):
            ax2 = plt.subplot(gslegend[i])
            plot_img(segnii, bg_img=epinii, axes=ax2, display_mode='z',
                     annotate=False, cut_coords=[c], threshold=0.1, cmap=mycolors,
                     interpolation='nearest')

    if output_file is not None:
        figure = plt.gcf()
        figure.savefig(output_file, bbox_inches='tight')
        plt.close(figure)
        figure = None
        return output_file

    return [ax0, ax1], gs


def spikesplot(ts_z, outer_gs=None, tr=None, zscored=True, spike_thresh=6., title='Spike plot',
               ax=None, cmap='viridis', hide_x=True, nskip=0):
    """
    A spikes plot. Thanks to Bob Dogherty (this docstring needs be improved with proper ack)
    """

    if ax is None:
        ax = plt.gca()

    if outer_gs is not None:
        gs = mgs.GridSpecFromSubplotSpec(1, 2, subplot_spec=outer_gs,
                                         width_ratios=[1, 100], wspace=0.0)
        ax = plt.subplot(gs[1])

    # Define TR and number of frames
    if tr is None:
        tr = 1.

    # Load timeseries, zscored slice-wise
    nslices = ts_z.shape[0]
    ntsteps = ts_z.shape[1]

    # Load a colormap
    my_cmap = cm.get_cmap(cmap)
    norm = Normalize(vmin=0, vmax=float(nslices - 1))
    colors = [my_cmap(norm(sl)) for sl in range(nslices)]

    stem = len(np.unique(ts_z).tolist()) == 2
    # Plot one line per axial slice timeseries
    for sl in range(nslices):
        if not stem:
            ax.plot(ts_z[sl, :], color=colors[sl], lw=0.5)
        else:
            markerline, stemlines, baseline = ax.stem(ts_z[sl, :])
            plt.setp(markerline, 'markerfacecolor', colors[sl])
            plt.setp(baseline, 'color', colors[sl], 'linewidth', 1)
            plt.setp(stemlines, 'color', colors[sl], 'linewidth', 1)

    # Handle X, Y axes
    ax.grid(False)

    # Handle X axis
    last = ntsteps - 1
    ax.set_xlim(0, last)
    xticks = list(range(0, last)[::20]) + [last] if not hide_x else []
    ax.set_xticks(xticks)

    if not hide_x:
        if tr is None:
            ax.set_xlabel('time (frame #)')
        else:
            ax.set_xlabel('time (s)')
            ax.set_xticklabels(
                ['%.02f' % t for t in (tr * np.array(xticks)).tolist()])

    # Handle Y axis
    ylabel = 'slice-wise noise average on background'
    if zscored:
        ylabel += ' (z-scored)'
        zs_max = np.abs(ts_z).max()
        ax.set_ylim((-(np.abs(ts_z[:, nskip:]).max()) * 1.05,
                     (np.abs(ts_z[:, nskip:]).max()) * 1.05))

        ytick_vals = np.arange(0.0, zs_max, float(np.floor(zs_max / 2.)))
        yticks = list(
            reversed((-1.0 * ytick_vals[ytick_vals > 0]).tolist())) + ytick_vals.tolist()

        # TODO plot min/max or mark spikes
        # yticks.insert(0, ts_z.min())
        # yticks += [ts_z.max()]
        for val in ytick_vals:
            ax.plot((0, ntsteps - 1), (-val, -val), 'k:', alpha=.2)
            ax.plot((0, ntsteps - 1), (val, val), 'k:', alpha=.2)

        # Plot spike threshold
        if zs_max < spike_thresh:
            ax.plot((0, ntsteps - 1), (-spike_thresh, -spike_thresh), 'k:')
            ax.plot((0, ntsteps - 1), (spike_thresh, spike_thresh), 'k:')
    else:
        yticks = [ts_z[:, nskip:].min(),
                  np.median(ts_z[:, nskip:]),
                  ts_z[:, nskip:].max()]
        ax.set_ylim(0, max(yticks[-1] * 1.05, (yticks[-1] - yticks[0]) * 2.0 + yticks[-1]))
        # ax.set_ylim(ts_z[:, nskip:].min() * 0.95,
        #             ts_z[:, nskip:].max() * 1.05)

    ax.annotate(
        ylabel, xy=(0.0, 0.7), xycoords='axes fraction',
        xytext=(0, 0), textcoords='offset points',
        va='center', ha='left', color='gray', size=4,
        bbox={'boxstyle': 'round', 'fc': 'w', 'ec': 'none', 'color': 'none',
              'lw': 0, 'alpha': 0.8})
    ax.set_yticks([])
    ax.set_yticklabels([])

    # if yticks:
    #     # ax.set_yticks(yticks)
    #     # ax.set_yticklabels(['%.02f' % y for y in yticks])
    #     # Plot maximum and minimum horizontal lines
    #     ax.plot((0, ntsteps - 1), (yticks[0], yticks[0]), 'k:')
    #     ax.plot((0, ntsteps - 1), (yticks[-1], yticks[-1]), 'k:')

    for side in ["top", "right"]:
        ax.spines[side].set_color('none')
        ax.spines[side].set_visible(False)

    if not hide_x:
        ax.spines["bottom"].set_position(('outward', 10))
        ax.xaxis.set_ticks_position('bottom')
    else:
        ax.spines["bottom"].set_color('none')
        ax.spines["bottom"].set_visible(False)

    # ax.spines["left"].set_position(('outward', 30))
    # ax.yaxis.set_ticks_position('left')
    ax.spines["left"].set_visible(False)
    ax.spines["left"].set_color(None)

    # labels = [label for label in ax.yaxis.get_ticklabels()]
    # labels[0].set_weight('bold')
    # labels[-1].set_weight('bold')
    if title:
        ax.set_title(title)
    return ax


def spikesplot_cb(position, cmap='viridis', fig=None):
    # Add colorbar
    if fig is None:
        fig = plt.gcf()

    cax = fig.add_axes(position)
    cb = ColorbarBase(cax, cmap=cm.get_cmap(cmap), spacing='proportional',
                      orientation='horizontal', drawedges=False)
    cb.set_ticks([0, 0.5, 1.0])
    cb.set_ticklabels(['Inferior', '(axial slice)', 'Superior'])
    cb.outline.set_linewidth(0)
    cb.ax.xaxis.set_tick_params(width=0)
    return cax


def confoundplot(tseries, gs_ts, gs_dist=None, name=None,
                 units=None, tr=None, hide_x=True, color='b', nskip=0,
                 cutoff=None, ylims=None):

    # Define TR and number of frames
    notr = False
    if tr is None:
        notr = True
        tr = 1.
    ntsteps = len(tseries)
    tseries = np.array(tseries)

    # Define nested GridSpec
    gs = mgs.GridSpecFromSubplotSpec(1, 2, subplot_spec=gs_ts,
                                     width_ratios=[1, 100], wspace=0.0)

    ax_ts = plt.subplot(gs[1])
    ax_ts.grid(False)

    # Set 10 frame markers in X axis
    interval = max((ntsteps // 10, ntsteps // 5, 1))
    xticks = list(range(0, ntsteps)[::interval])
    ax_ts.set_xticks(xticks)

    if not hide_x:
        if notr:
            ax_ts.set_xlabel('time (frame #)')
        else:
            ax_ts.set_xlabel('time (s)')
            labels = tr * np.array(xticks)
            ax_ts.set_xticklabels(['%.02f' % t for t in labels.tolist()])
    else:
        ax_ts.set_xticklabels([])

    if name is not None:
        if units is not None:
            name += ' [%s]' % units

        ax_ts.annotate(
            name, xy=(0.0, 0.7), xytext=(0, 0), xycoords='axes fraction',
            textcoords='offset points', va='center', ha='left',
            color=color, size=8,
            bbox={'boxstyle': 'round', 'fc': 'w', 'ec': 'none',
                  'color': 'none', 'lw': 0, 'alpha': 0.8})

    for side in ["top", "right"]:
        ax_ts.spines[side].set_color('none')
        ax_ts.spines[side].set_visible(False)

    if not hide_x:
        ax_ts.spines["bottom"].set_position(('outward', 20))
        ax_ts.xaxis.set_ticks_position('bottom')
    else:
        ax_ts.spines["bottom"].set_color('none')
        ax_ts.spines["bottom"].set_visible(False)

    # ax_ts.spines["left"].set_position(('outward', 30))
    ax_ts.spines["left"].set_color('none')
    ax_ts.spines["left"].set_visible(False)
    # ax_ts.yaxis.set_ticks_position('left')

    ax_ts.set_yticks([])
    ax_ts.set_yticklabels([])

    nonnan = tseries[~np.isnan(tseries)]
    if nonnan.size > 0:
        # Calculate Y limits
        valrange = (nonnan.max() - nonnan.min())
        def_ylims = [nonnan.min() - 0.1 * valrange, nonnan.max() + 0.1 * valrange]
        if ylims is not None:
            if ylims[0] is not None:
                def_ylims[0] = min([def_ylims[0], ylims[0]])
            if ylims[1] is not None:
                def_ylims[1] = max([def_ylims[1], ylims[1]])

        # Add space for plot title and mean/SD annotation
        def_ylims[0] -= 0.1 * (def_ylims[1] - def_ylims[0])

        ax_ts.set_ylim(def_ylims)

        # Annotate stats
        maxv = nonnan.max()
        mean = nonnan.mean()
        stdv = nonnan.std()
        p95 = np.percentile(nonnan, 95.0)
    else:
        maxv = 0
        mean = 0
        stdv = 0
        p95 = 0

    stats_label = (r'max: {max:.3f}{units} $\bullet$ mean: {mean:.3f}{units} '
                   r'$\bullet$ $\sigma$: {sigma:.3f}').format(
        max=maxv, mean=mean, units=units or '', sigma=stdv)
    ax_ts.annotate(
        stats_label, xy=(0.98, 0.7), xycoords='axes fraction',
        xytext=(0, 0), textcoords='offset points',
        va='center', ha='right', color=color, size=4,
        bbox={'boxstyle': 'round', 'fc': 'w', 'ec': 'none', 'color': 'none',
              'lw': 0, 'alpha': 0.8}
    )

    # Annotate percentile 95
    ax_ts.plot((0, ntsteps - 1), [p95] * 2, linewidth=.1, color='lightgray')
    ax_ts.annotate(
        '%.2f' % p95, xy=(0, p95), xytext=(-1, 0),
        textcoords='offset points', va='center', ha='right',
        color='lightgray', size=3)

    if cutoff is None:
        cutoff = []

    for i, thr in enumerate(cutoff):
        ax_ts.plot((0, ntsteps - 1), [thr] * 2,
                   linewidth=.2, color='dimgray')

        ax_ts.annotate(
            '%.2f' % thr, xy=(0, thr), xytext=(-1, 0),
            textcoords='offset points', va='center', ha='right',
            color='dimgray', size=3)

    ax_ts.plot(tseries, color=color, linewidth=.8)
    ax_ts.set_xlim((0, ntsteps - 1))

    if gs_dist is not None:
        ax_dist = plt.subplot(gs_dist)
        sns.displot(tseries, vertical=True, ax=ax_dist)
        ax_dist.set_xlabel('Timesteps')
        ax_dist.set_ylim(ax_ts.get_ylim())
        ax_dist.set_yticklabels([])

        return [ax_ts, ax_dist], gs
    return ax_ts, gs


def compcor_variance_plot(metadata_files, metadata_sources=None,
                          output_file=None, varexp_thresh=(0.5, 0.7, 0.9),
                          fig=None):
    """
    Parameters
    ----------
    metadata_files: list
        List of paths to files containing component metadata. If more than one
        decomposition has been performed (e.g., anatomical and temporal
        CompCor decompositions), then all metadata files can be provided in
        the list. However, each metadata file should have a corresponding
        entry in `metadata_sources`.
    metadata_sources: list or None
        List of source names (e.g., ['aCompCor']) for decompositions. This
        list should be of the same length as `metadata_files`.
    output_file: str or None
        Path where the output figure should be saved. If this is not defined,
        then the plotting axes will be returned instead of the saved figure
        path.
    varexp_thresh: tuple
        Set of variance thresholds to include in the plot (default 0.5, 0.7,
        0.9).
    fig: figure or None
        Existing figure on which to plot.

    Returns
    -------
    ax: axes
        Plotting axes. Returned only if the `output_file` parameter is None.
    output_file: str
        The file where the figure is saved.
    """
    metadata = {}
    if metadata_sources is None:
        if len(metadata_files) == 1:
            metadata_sources = ['CompCor']
        else:
            metadata_sources = ['Decomposition {:d}'.format(i)
                                for i in range(len(metadata_files))]
    for file, source in zip(metadata_files, metadata_sources):
        metadata[source] = pd.read_csv(str(file), sep=r'\s+')
        metadata[source]['source'] = source
    metadata = pd.concat(list(metadata.values()))
    bbox_txt = {
        'boxstyle': 'round',
        'fc': 'white',
        'ec': 'none',
        'color': 'none',
        'linewidth': 0,
        'alpha': 0.8
    }

    decompositions = []
    data_sources = list(metadata.groupby(['source', 'mask']).groups.keys())
    for source, mask in data_sources:
        if not np.isnan(
                metadata.loc[
                    (metadata['source'] == source) & (metadata['mask'] == mask)
                ]['singular_value'].values[0]):
            decompositions.append((source, mask))

    if fig is not None:
        ax = [fig.add_subplot(1, len(decompositions), i + 1)
              for i in range(len(decompositions))]
    elif len(decompositions) > 1:
        fig, ax = plt.subplots(1, len(decompositions),
                               figsize=(5 * len(decompositions), 5))
    else:
        ax = [plt.axes()]

    for m, (source, mask) in enumerate(decompositions):
        components = metadata[(metadata['mask'] == mask) & (metadata['source'] == source)]
        if len([m for s, m in decompositions if s == source]) > 1:
            title_mask = ' ({} mask)'.format(mask)
        else:
            title_mask = ''
        fig_title = '{}{}'.format(source, title_mask)

        ax[m].plot(np.arange(components.shape[0] + 1), [0] + list(
            100 * components['cumulative_variance_explained']),
            color='purple',
            linewidth=2.5)
        ax[m].grid(False)
        ax[m].set_xlabel('number of components in model')
        ax[m].set_ylabel('cumulative variance explained (%)')
        ax[m].set_title(fig_title)

        varexp = {}

        for i, thr in enumerate(varexp_thresh):
            varexp[thr] = np.atleast_1d(np.searchsorted(
                components['cumulative_variance_explained'], thr)) + 1
            ax[m].axhline(y=100 * thr, color='lightgrey', linewidth=0.25)
            ax[m].axvline(x=varexp[thr], color='C{}'.format(i),
                          linewidth=2, linestyle=':')
            ax[m].text(0, 100 * thr, '{:.0f}'.format(100 * thr),
                       fontsize='x-small', bbox=bbox_txt)
            ax[m].text(varexp[thr][0], 25,
                       '{} components explain\n{:.0f}% of variance'.format(
                       varexp[thr][0], 100 * thr),
                       rotation=90,
                       horizontalalignment='center',
                       fontsize='xx-small',
                       bbox=bbox_txt)

        ax[m].set_yticks([])
        ax[m].set_yticklabels([])
        for tick in ax[m].xaxis.get_major_ticks():
            tick.label.set_fontsize('x-small')
            tick.label.set_rotation('vertical')
        for side in ['top', 'right', 'left']:
            ax[m].spines[side].set_color('none')
            ax[m].spines[side].set_visible(False)

    if output_file is not None:
        figure = plt.gcf()
        figure.savefig(output_file, bbox_inches='tight')
        plt.close(figure)
        figure = None
        return output_file
    return ax


def confounds_correlation_plot(confounds_file, output_file=None, figure=None,
                               reference='global_signal', max_dim=70):
    """
    Parameters
    ----------
    confounds_file: str
        File containing all confound regressors to be included in the
        correlation plot.
    output_file: str or None
        Path where the output figure should be saved. If this is not defined,
        then the plotting axes will be returned instead of the saved figure
        path.
    figure: figure or None
        Existing figure on which to plot.
    reference: str
        `confounds_correlation_plot` prepares a bar plot of the correlations
        of each confound regressor with a reference column. By default, this
        is the global signal (so that collinearities with the global signal
        can readily be assessed).
    max_dim: int
        The maximum number of regressors to be included in the output plot.
        Reductions (e.g., CompCor) of high-dimensional data can yield so many
        regressors that the correlation structure becomes obfuscated. This
        criterion selects the `max_dim` regressors that have the largest
        correlation magnitude with `reference` for inclusion in the plot.

    Returns
    -------
    axes and gridspec
        Plotting axes and gridspec. Returned only if `output_file` is None.
    output_file: str
        The file where the figure is saved.
    """
    confounds_data = pd.read_table(confounds_file)
    confounds_data = confounds_data.loc[:, np.logical_not(
        np.isclose(confounds_data.var(skipna=True), 0))]
    corr = confounds_data.corr()

    gscorr = corr.copy()
    gscorr['index'] = gscorr.index
    gscorr[reference] = np.abs(gscorr[reference])
    gs_descending = gscorr.sort_values(by=reference,
                                       ascending=False)['index']
    n_vars = corr.shape[0]
    max_dim = min(n_vars, max_dim)

    gs_descending = gs_descending[:max_dim]
    features = [p for p in corr.columns if p in gs_descending]
    corr = corr.loc[features, features]
    np.fill_diagonal(corr.values, 0)

    if figure is None:
        plt.figure(figsize=(15, 5))
    gs = mgs.GridSpec(1, 21)
    ax0 = plt.subplot(gs[0, :10])
    ax1 = plt.subplot(gs[0, 11:])

    mask = np.zeros_like(corr, dtype=np.bool)
    mask[np.triu_indices_from(mask)] = True
    sns.heatmap(corr,
                linewidths=0.5,
                cmap='coolwarm',
                center=0,
                square=True,
                ax=ax0)
    ax0.tick_params(axis='both', which='both', width=0)

    for tick in ax0.xaxis.get_major_ticks():
        tick.label.set_fontsize('small')
    for tick in ax0.yaxis.get_major_ticks():
        tick.label.set_fontsize('small')
    sns.barplot(data=gscorr,
                x='index',
                y=reference,
                ax=ax1,
                order=gs_descending,
                palette='Reds_d',
                saturation=.5)

    ax1.set_xlabel('Confound time series')
    ax1.set_ylabel('Magnitude of correlation with {}'.format(reference))
    ax1.tick_params(axis='x', which='both', width=0)
    ax1.tick_params(axis='y', which='both', width=5, length=5)

    for tick in ax1.xaxis.get_major_ticks():
        tick.label.set_fontsize('small')
        tick.label.set_rotation('vertical')
    for tick in ax1.yaxis.get_major_ticks():
        tick.label.set_fontsize('small')
    for side in ['top', 'right', 'left']:
        ax1.spines[side].set_color('none')
        ax1.spines[side].set_visible(False)

    if output_file is not None:
        figure = plt.gcf()
        figure.savefig(output_file, bbox_inches='tight')
        plt.close(figure)
        figure = None
        return output_file
    return [ax0, ax1], gs
