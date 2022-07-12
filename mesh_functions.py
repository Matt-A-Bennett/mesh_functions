import nibabel
import numpy as np
import networkx as nx
import itertools
import matplotlib.pyplot as plt

def handle_ext(ext):
    if ext[0] != '.':
        ext = f'.{ext}'
    return ext


def get_surf_data(data_obj, ext):
    if ext == '.gii':
        data_array = data_obj.darrays[0].data
    elif ext == '.mgh':
        data_array = data_obj.get_data()
    return data_array


def load_surface_info(nifti_name):
    # each row of mesh_faces are the nodes that define that face
    _, mesh_faces = nibabel.freesurfer.io.read_geometry(nifti_name)
    nodes_to_add = np.unique(mesh_faces)
    return mesh_faces, nodes_to_add


def nifti_to_graph(nifti_name, mesh_faces=None, nodes_to_add=None):
    if mesh_faces is None or nodes_to_add is None:
        mesh_faces, nodes_to_add = load_surface_info(nifti_name)

    G = nx.Graph()
    # construct the graph nodes and edges
    G.add_nodes_from(nodes_to_add)
    for i, row in enumerate(mesh_faces):
        G.add_edges_from(list(itertools.combinations(row, 2)))

    return G


def load_map_data(map_name, ext):
    data_obj = nibabel.load(f'{map_name}{ext}')

    # This gives a one-dimensional array of (N,) - for one per node
    map_data = get_surf_data(data_obj, ext)

    return map_data


def add_map_to_surface(G, nodes_to_map, map_name, ext):
    ext = handle_ext(ext)

    map_data = load_map_data(map_name, ext)

    # data colors to node colors:
    color_map = map_data[nodes_to_map]

    # dictionary of attributes to add to graph
    color_map_dict = {}
    for i, color in zip(G.nodes, color_map):
        color_map_dict[i] = {"map_val": color}

    # add the attributes
    nx.set_node_attributes(G, color_map_dict)

    return G


def surf_and_map_to_graph(nifti_name, map_name, ext):
    mesh_faces, nodes_to_add = load_surface_info(nifti_name)
    G = nifti_to_graph(nifti_name, mesh_faces, nodes_to_add)
    G = add_map_to_surface(G, nodes_to_add, map_name, ext)
    return G


def get_node_attributes_as_list(G, nodes=None, key=None):
    '''Extract node attributes: from dictionary take the values based on <key>
    (which must by a string).'''
    if not nodes:
        nodes = G.nodes()
    # extract attribute
    tmp = []
    for i in nodes:
        tmp.append(G.nodes[i][key])
    return tmp


def graph_has_attributes(G):
    return G.nodes[0] != {}


def get_map_data_as_list(G):
    map_data = get_node_attributes_as_list(G, list(G.nodes), key='map_val')
    map_data = [np.float(x) for x in map_data]
    return map_data


def get_neighbours_and_vals(G, nodes):
    '''Get neighbours and associated values of set of nodes as dictionary'''
    if isinstance(nodes, int):
        nodes = [nodes]
    node_neighbours = []
    vals = []
    for node in nodes:
        for neighbours, _ in G.adj[node].items():
            node_neighbours.append(neighbours)
            vals.append(G.nodes[neighbours]["map_val"])
    return dict(zip(node_neighbours, vals))


def get_multi_neighbours_and_vals(G, nodes, neighbourhood_size):
    neighbourhood = {}
    for i in range(neighbourhood_size):
        neighbours = get_neighbours_and_vals(G, nodes)
        neighbourhood.update(neighbours)
    return neighbourhood


def is_node_on_region_border(G, region_nodes, node):
    '''For a graph <G>, and a patch-like subset of its nodes <region_nodes>,
    does a particular <node> lay on the border of that subset?'''
    neighbours = get_neighbours_and_vals(G, [node])
    total_neighbours = len(set(neighbours.keys()))
    n_nodes_in_region = len(set(neighbours.keys()).intersection(label_coords))
    return n_nodes_in_region < total_neighbours


def find_region_border(G, nodes):
    '''Return the nodes that have neighbours in the graph that don't appear in
    the original set of nodes'''
    border_nodes = []
    for node in nodes:
        if is_node_on_region_border(G, nodes, node):
            border_nodes.append(node)
    return border_nodes


def remove_out_of_region_nodes(G, region_nodes, nodes):
    # intersection is taking the overlapping part in a venn diagram
    return list(set(region_nodes).intersection(set(nodes)))


def expand_nodes(G, nodes, stepsize=1, ignore_nans=False):
    orig_nodes = nodes[:]
    for i in range(stepsize):
        neighbours = get_neighbours_and_vals(G, nodes)
        if ignore_nans:
            neighbours = [k for k,v in neighbours.items() if not np.isnan(v)]
        else:
            neighbours = neighbours.keys()
        nodes += neighbours
    new_nodes=list(set(nodes)-set(orig_nodes))
    return nodes, new_nodes


# will be useful for gradient ascent
def max_neighbour(G, node, neighbourhood_size=1):
    '''Return node with maximum map value amoung neighbours (and neighbours of
    neighbours etc...)'''
    neighbours = get_multi_neighbours_and_vals(G, [node], neighbourhood_size)
    return (max(neighbours, key=neighbours.get), max(neighbours.values()))


# makes the whole path to take a step in the right direction
# each node here is treated independently
def nodes_gradient_step(G, nodes, stepsize=1):
    '''Return new nodes positions where each node is replaced by that node's
    maximum neighbour in <stepsize>'''
    map_values = get_node_attributes_as_list(G, nodes, key="map_val")
    new_positions = []
    for node, retval in zip(nodes, map_values):
        max_info = max_neighbour(G, node, neighbourhood_size=stepsize)
        if retval < max_info[1]:
            new_positions.append(max_info[0])
        else:
            new_positions.append(node)
    return new_positions


def smooth_graph(G, nodes=None, n_its=1, kernel_size=1):
    '''Smooth all nodes of map (replace each node with mean of neighbours)'''
    if not isinstance(nodes, list):
        nodes = G.nodes()
    G_smooth = G.copy()
    for it in range(n_its):
        print(f'Smoothing iteration: {it+1}/{n_its}')
        color_map_dict = {}
        for node in nodes:
            out = get_multi_neighbours_and_vals(G_smooth, [node], kernel_size)
            mean = np.nanmean(list(out.values()))
            color_map_dict[node] = {"map_val": mean}
        nx.set_node_attributes(G_smooth, color_map_dict)
    return G_smooth


def define_map_clusters(G):
    map_data = get_map_data_as_list(G)
    for x in map_data:
        get_neighbours_and_vals(G, nodes)
    pass


# some functions for plotting
def set3Dview(ax):
    ax.set_xlim(-100, 100)
    ax.set_ylim(-100, 100)
    ax.set_zlim(-100, 100)
    ax.set_facecolor('black')
    ax.set_box_aspect((1,1,1))
    return None


def setzoomed3Dview(ax):
    set3Dview()
    ax.azim =-77.20329531963876
    ax.elev =-3.8354678562436106
    ax.dist = 2.0
    return None


def plot_nodes(G, nifti_name, node_sets=None, colors = ['white', 'black', 'pink']):
    '''nodes_sets is a list of upto 3 sets of nodes to draw - each will have a
    different colour'''

    mesh_coords, _ = nibabel.freesurfer.io.read_geometry(nifti_name)

    if graph_has_attributes(G):
        map_data = get_map_data_as_list(G)

        map_data = [0 if np.isnan(x) else x for x in map_data]

        ax = plt.axes(projection='3d')
        ax.scatter3D(mesh_coords[:, 0], mesh_coords[:, 1],
                     mesh_coords[:, 2], s=1, c=map_data, cmap='jet')

    if node_sets is not None:
        for nodes, color in zip(node_sets, colors):
            ax.scatter3D(mesh_coords[nodes, 0], mesh_coords[nodes, 1],
                         mesh_coords[nodes, 2], marker='o', s=30, c=color)

    set3Dview(ax)
    return ax

