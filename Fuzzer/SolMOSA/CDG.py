"""
This Module contains all code necessary for creating and interacting a \
Control-Dependency-Graph and interacting with it.

Classes:
CompactNode:    A node in the Control-Dependency-Graph.
CompactEdge:    An edge in the Control-Dependency-Graph.
Predicate:      A predicate that controls the Edges leading out of a node.
CDG:            A Control-Dependency-Graph.
"""

import logging
import configparser
import re
# import sys
# import numpy as np
from evm_cfg_builder.cfg import CFG
from operator import attrgetter


class CompactNode():
    """
    A node in a control-dependency-graph.

    Properties:
    node_id:        An id of the node, consisting of the method name and a
                    number that increases the deeper in a method the node is.
    all_node_ids:   If a node is shared by different methods, this set
                    stores the id it would have in other methods than the
                    node_id.
    start_pc:       The pc of first Opcode in the CompactNode.
    end_pc:         The pc of the last Opcode in the CompactNode.
    basic_blocks:   The list of basic_blocks that are in the CompactNode.
    inc_node_ids:   The node_id's of CompactNodes that have edges leading into
                    this node.
    outg_node_ids:  The node_id's of CompactNodes that are connected to this
                    Node through outgoing Edges.
    predicate:      The predicate in this node that is controlling any Edges
                    leaving from it in the CDG.
    semi:           The semidominator, used for the Lengauer-Tarjan algorithm.
    bucket:         The set of nodes for which this node is the semidominator
    dom:            The immediate dominator of this node.
    ancestor:       One of the ancestors of the vertex, used for the
                    Lengauer-Tarjan algorithm
    """

    node_id = ("", 0)
    all_node_ids = None
    start_pc = 0
    end_pc = 0
    basic_blocks = []
    inc_node_ids = []
    outg_node_ids = []
    predicate = None
    semi = 0
    bucket = set()
    dom = None
    ancestor = None
    label = None

    def __init__(self, _node_id, _all_node_ids, _start_pc, _end_pc,
                 _basic_blocks, _inc_node_ids, _outg_node_ids, _predicate=None,
                 _semi=0, _bucket=set(), _dom=None):
        """Initialise a CompactNode by passing some elements explicitly."""
        self.node_id = _node_id
        self.all_node_ids = _all_node_ids
        self.start_pc = _start_pc
        self.end_pc = _end_pc
        self.basic_blocks = _basic_blocks
        self.inc_node_ids = _inc_node_ids
        self.outg_node_ids = _outg_node_ids
        self.predicate = _predicate
        self.semi = _semi
        self.bucket = set()
        self.dom = _dom
        self.ancestor = None
        self.label = 0

    def show_CompactNode(self, log=False):
        """Print all the information of the CompactNode."""
        info = "Node_id: {}".format(self.node_id) + "\n\tstart_pc: {}"\
            .format(self.start_pc) + "\n\tend_pc: {}".format(self.end_pc) \
            + "\n\tincoming node ids: {}".format(self.inc_node_ids) + \
            "\n\toutgoing node ids: {}".format(self.outg_node_ids)
        if len(self.all_node_ids) > 1:
            info = info + "\nall node ids: {}".format(list(self.all_node_ids))

        if log:
            logging.info(info)
        else:
            print(info)


class CompactEdge():
    """
    An edge in a control-dependency-graph.

    Properties:
    startNode_id:   The Node_id of the starting point of the edge.
    endNode_id:     The Node_id of the end point of the edge.
    predicate:      The predicate object that controls whether this edge is
                    traversed or not.
    """

    startNode_id = None
    endNode_id = None
    predicate = None

    def __init__(self, _startNode_id, _endNode_id, _predicate):
        """Initialise a CompactEdge."""
        self.startNode_id = _startNode_id
        self.endNode_id = _endNode_id
        self.predicate = _predicate

    def __eq__(self, other):
        """Two CompactEdges are equal iff their startNode_id and endNode_id \
        are equal."""
        return ((self.startNode_id == other.startNode_id) &
                (self.endNode_id == other.endNode_id))

    def __hash__(self):
        """Hash function."""
        return hash((self.startNode_id, self.endNode_id))

    def show_CompactEdge(self, log=False):
        """Show all information of the Edge."""
        if self.predicate is None:
            info = "Edge from {}, to {} ".format(self.startNode_id,
                                                 self.endNode_id)
        else:
            info = "Edge from {}, to {} with predicate {}".format(
                self.startNode_id, self.endNode_id, self.predicate.eval)
        if log:
            logging.info(info)
        else:
            print(info)


class Predicate():
    """
    A predicate that controls Edges in a control-flow-graph.

    Properties:
    eval:       The string corresponding to the Opcode of the predicate.
    pc:         The pc of the predicate in the deployed bytecode.
    node_id:    The node_id of the CompactNode in which the predicate can be
                found.
    """

    eval = ""
    pc = 0
    node_id = None

    def __init__(self, _eval, _pc, _node_id):
        """Initialise Predicate."""
        self.eval = _eval
        self.pc = _pc
        self.node_id = _node_id

    def show_Predicate(self, verbose=True):
        """Show Predicate."""
        info = "Predicate with eval: {}, at pc: {} and node_id: {}".format(
            self.eval, self.pc, self.node_id)
        if(verbose):
            print(info)
        else:
            return info


class CDG():
    """
    A control-dependency-graph object created using the evm_cfg_builder tool.

    Properties:
        - name:         The name of the corresponding Smart Contract.
        - CompactNodes: A list of all the CompactNodes in the CDG.
        - CompactEdges: A list of all the CompactEdges in the CDG.
        - StartNodes:   The CompactNodes that are the start of a method.
        - vertex:       An ordered list of vertices used for the
                        Lengauer-Tarjan algorithm.
        - n:            A global counter used for the Lengauer-Tarjan algorithm
    """

    name = ""
    CompactNodes = []
    CompactEdges = []
    StartNodes = []
    vertex = []
    n = 0

    def __init__(self, _name, _bytecode, _predicates):
        """
        Create a control-dependency-graph by going through all the methods in \
        the smart contract and extracing their (start-)nodes and edges.

        Arguments:
        _name:          The name of the smart contract under investigation
        _bytecode:      The deployed bytecode of the smart contract under
                        investigation.
        _predicates:    The relevant Opcodes for the predicates that control
                        branches.
        """
        cfg = CFG(_bytecode)
        N = []
        s = []
        payableMethodNames = []
        methods = [method for method in cfg.functions]

        double_nodes = {}
        simple_E = {}
        for method in methods:
            bbs = cfg.basic_blocks.copy()
            node_ctr = 0
            N, method_sEdges, double_nodes = self.Compactify_method(
                method, node_ctr, bbs, [], N, simple_E, double_nodes)
            simple_E.update(method_sEdges)

            # Check if the method is payable
            if 'payable' in method.attributes:
                payableMethodNames.append(method.name)

        N = self.Merge_Double_Nodes(double_nodes)
        N = self.Add_incoming_outgoing_node_ids(N, simple_E)
        N = self.Remove_Invalid_Nodes(N)
        E, s = self.Find_Compact_Edges_StartPoints(N)

        if 'payable' not in method.attributes:
            N, E = self.Payable_Check(N, E, payableMethodNames)

        self.name = _name
        self.CompactNodes = N
        self.CompactEdges = E
        self.StartNodes = s
        self.vertex = [None] * len(self.CompactNodes)
        self.n = 0

    def Payable_Check(self, cNodes, cEdges, _payableMethodNames):
        """
        During compilation of Solidity code, extra nodes are created that \
        revert the transaction if some Ether is send to a nonpayable method, \
        these are not of interest to our control-dependency-graph and can be \
        safely removed.

        Arguments:
            - cNodes: the compact nodes of the compactified CFG.
            - cEdges: the compact edges of the compactified CFG.
        Outputs:
            - relNodes: the relevant compact nodes.
            - relEdges: the relevant compact edges.
        """
        mergeNodes = set()
        irrelNodes = set()
        for cNode in cNodes:
            # Removes the extra reverts that result from nonpayable functions
            if (cNode.basic_blocks[-1].instructions[-1].name == "REVERT") & \
                ('_dispatcher' not in [node_id[0] for
                                       node_id in list(cNode.all_node_ids)]) &\
                    (not bool(set(node_id[0] for node_id in
                                  list(cNode.all_node_ids)).intersection(
                        set(_payableMethodNames)))):

                assert len(cNode.outg_node_ids) == 0, \
                    "Node {} ends with a REVERT OpCode but also has outgoing \
                    nodes?!".format(cNode.node_id)

                isExtraNode = False
                for incNode in [iNode for iNode in cNodes if iNode.node_id in
                                cNode.inc_node_ids]:
                    if 1 in [node_id[1] for node_id in
                             list(incNode.all_node_ids)]:
                        if len(cNode.inc_node_ids) > 1:
                            for inc_to_extra_Node in \
                                    [iNode for iNode in cNodes if
                                     iNode.node_id in cNode.inc_node_ids]:
                                inc_to_extra_Node.outg_node_ids\
                                    .remove(cNode.node_id)
                        else:
                            incNode.outg_node_ids.remove(cNode.node_id)
                        irrelNodes = irrelNodes.union(set([cNode]))
                        isExtraNode = True
                if isExtraNode:
                    cNodes, pNodes, newMergeNodes, newIrrelNodes = self.\
                        getMergeNodes(cNodes, set([pNode for pNode in
                                                   cNodes if pNode.node_id in
                                                   cNode.inc_node_ids]), set(),
                                      set())
                    mergeNodes = mergeNodes.union(newMergeNodes)
                    irrelNodes = irrelNodes.union(newIrrelNodes)

        relNodes = list(set(cNodes) - irrelNodes)
        relNode_ids = [relNode.node_id for relNode in relNodes]
        relEdges = [cEdge for cEdge in cEdges if
                    (cEdge.endNode_id in relNode_ids) |
                    (cEdge.startNode_id in relNode_ids)]

        mergenodeList = sorted(list(mergeNodes), key=attrgetter('node_id'),
                               reverse=True)

        for mergeNode in mergenodeList:
            if len(mergeNode.outg_node_ids) != 1:
                logging.warning("After removing a REVERT-ing node, it's "
                                "parent node has {} outgoing nodes. Parent "
                                "starts at {} and ends at {}. This could be "
                                "due to an empty fallback which is not "
                                "ignored.".format(
                                    len(mergeNode.outg_node_ids),
                                    mergeNode.start_pc, mergeNode.end_pc))
                relEdges = [relEdge for relEdge in relEdges if
                            relEdge.startNode_id != mergeNode.node_id]
                for relNode in relNodes:
                    if mergeNode.node_id in relNode.outg_node_ids:
                        if len(relNode.outg_node_ids) == 1:
                            relNode.outg_node_ids = []
                        else:
                            relNode.outg_node_ids.remove(mergeNode.node_id)
            else:
                nextNode = [nNode for nNode in cNodes if nNode.node_id in
                            mergeNode.outg_node_ids][0]
                assert len(nextNode.inc_node_ids) == 1, \
                    "After removing a REVERT-ing node the other child of it's \
                    parent still had {} incoming nodes"\
                    .format(len(nextNode.inc_node_ids))

                mergeNode.end_pc = nextNode.end_pc
                mergeNode.basic_blocks = mergeNode.basic_blocks \
                    + nextNode.basic_blocks
                mergeNode.outg_node_ids = nextNode.outg_node_ids

                relEdges = [relEdge for relEdge in relEdges if
                            relEdge.startNode_id != mergeNode.node_id]

                for relEdge in relEdges:
                    if (relEdge.startNode_id == nextNode.node_id) & \
                            ('_dispatcher' not in
                             [node_id[0] for node_id in
                              list(nextNode.all_node_ids)]):
                        relEdge.startNode_id = mergeNode.node_id

                relNodes = [relNode for relNode in relNodes if (
                    relNode.node_id != mergeNode.node_id) &
                    (relNode.node_id != nextNode.node_id)]
                for relNode in relNodes:
                    if nextNode.node_id in relNode.inc_node_ids:
                        relNode.inc_node_ids.remove(nextNode.node_id)
                        relNode.inc_node_ids = relNode.inc_node_ids \
                            + [mergeNode.node_id]
                relNodes = relNodes + [mergeNode]

        return relNodes, relEdges

    def getMergeNodes(self, _cNodes, _pNodes, _mergeNodes, _irrelNodes):
        """
        Get Nodes that can be merged.

        The mergenodes are those nodes who have exactly two children: one \
        child is relevant and the other child will be part of a single branch \
        that leads to REVERT and is therefore irrelevant. This function looks \
        at all the parents of child that is part of a single branch that \
        leads to a REVERT and checks whether they are mergenodes, or if they \
        are irrelevant in which case their parents might be mergenodes. At \
        the same time, this function removes childNodes from the mergedNodes \
        and in doing so updates cNodes.

        Arguments:
        cNodes:     the current list of compactNodes
        pNodes:     the current list of parent Nodes that are potentially
                    mergenodes
        mergeNodes: the currently identified mergenodes
        irrelNodes: the currently identified irrelevant nodes
        Outputs:
            see Arguments
        """
        if not bool(_pNodes):
            # If _pNodes is the emptyset
            return _cNodes, set(), _mergeNodes, _irrelNodes
        else:
            pNode = _pNodes.pop()

        if len(pNode.outg_node_ids) > 1:
            # The parent node has multiple children after removing the
            # irrelevant child.
            return self.getMergeNodes(
                _cNodes, _pNodes, _mergeNodes, _irrelNodes)
        elif len(pNode.outg_node_ids) > 0:
            # The parent has exactly 1 child after removing the irrelevant
            # child, therefore it could potentially be merged
            assert len(
                pNode.outg_node_ids) == 1,\
                "After removing a REVERT-ing node, it's parent node has {} \
            outgoing nodes".format(
                len(pNode.outg_node_ids))
            nextNode = [nNode for nNode in _cNodes if nNode.node_id in
                        pNode.outg_node_ids][0]
            if len(nextNode.inc_node_ids) > 1:
                # The parents only child has multiple parents,
                # no merging is needed.
                return self.getMergeNodes(
                    _cNodes, _pNodes, _mergeNodes, _irrelNodes, _irrelNodes)
            else:
                # The parent's only child has only one parent:
                # they should be merged.
                return self.getMergeNodes(_cNodes, _pNodes, set([pNode]).union(
                    _mergeNodes), _irrelNodes)
        else:
            # The parent has 0 children after removing the irrelevant child:
            # it is itself irrelevant
            irrelNodes = _irrelNodes.union(set([pNode]))
            nextpNodes = [npNode for npNode in _cNodes if npNode.node_id in
                          pNode.outg_node_ids]
            for nextpNode in nextpNodes:
                nextpNode.outg_node_ids.remove(pNode.node_id)
            pNodes = _pNodes.union(set(nextpNodes))
            return self.getMergeNodes(_cNodes, pNodes, _mergeNodes, irrelNodes)

    def Compactify_method(
            self, method, node_ctr, bbs, rbbs, compactNodes, simple_edges,
            _double_nodes):
        """
        Extract the compactified nodes and a first version of the edges \
        between them in a recursive manner for a given method.

        Arguments:
        method:       A function object of the control-flow-graph
        node_ctr:     Counts the number of nodes in this method and gives them
                      a unique id.
        bbs:          The basic blocks of the control-flow-graph that have not
                      yet been added to a CompactNode.
        rbbs:         The basic blocks of the control-flow-graph that have been
                      removed from bbs because they have been added to a
                      CompactNode
        compactNodes: A list of the CompactNodes that have been created for
                      this and previous methods.
        simple_edges: A dictionary of edges with starting point denoted by the
                      corresponding CompactNode_id and end points denoted by
                      the start_pcs of the corresponding basic_blocks.
        _double_nodes:    A dictionary with keys of all start_pc's of all
                      compactNodes that have been found and values of all
                      compactNodes that have been found.

        Outputs:
        compactNodes: A list of all the CompactNodes in this method.
        simple_edges: A dictionary of edges with starting point denoted by the
                      corresponding CompactNode_id and end points denoted by
                      the start_pcs of the corresponding basic_blocks.
        """
        double_nodes = _double_nodes
        sb, bbs, rbbs, found = self.Find_Starting_Node(method, bbs, rbbs)
        node_ctr += 1
        if not found:
            assert(len(rbbs) == len(method.basic_blocks)), \
                "No starting blocks were found but there are stil basic "\
                "blocks should be added to the control-dependency-graph!"
            return compactNodes, simple_edges, double_nodes
        else:
            start_pc = sb.start.pc
            bbs, rbbs, end_pc, basic_blocks, outg_node_startpcs = \
                self.Compactify_Basic_Blocks(method, sb, bbs, rbbs, [])
            if start_pc in double_nodes.keys():
                cNode = next((compactNode for compactNode in compactNodes if
                              compactNode.start_pc == start_pc), None)
                assert cNode is not None, \
                    f"There was a start_pc ({start_pc}) in start_pcs without "\
                    "a corresponding compactNode in compactNodes."
                assert cNode.end_pc == end_pc, "Two compactNodes were found "\
                    f"with the same start_pc's ({start_pc}), but different "\
                    f"end_pc's ({cNode.end_pc}) and ({end_pc}). "\
                    f"Original node: {cNode.node_id}, New is in {method.name}."
                assert outg_node_startpcs == simple_edges[cNode.node_id], \
                    "When creating double nodes, the simple_edges should "\
                    "be the same!"

            # Create and add a new CompactNode
            node_id = (method.name, node_ctr)
            new_cNode = CompactNode(
                node_id, set(
                    [node_id]), start_pc, end_pc, basic_blocks, [], [])
            if start_pc not in double_nodes.keys():
                double_nodes[start_pc] = [new_cNode]
            else:
                double_nodes[start_pc] = double_nodes[start_pc] + [new_cNode]

            simple_edges[node_id] = outg_node_startpcs
            compactNodes = compactNodes + [new_cNode]
            return self.Compactify_method(
                method, node_ctr, bbs, rbbs, compactNodes, simple_edges,
                double_nodes)

    def Find_Starting_Node(self, method, bbs, rbbs):
        """
        Find and return the next basic_block that can be reached by any of \
        the CompactNodes that have already been created within the method \
        or return None, if no such basic_block can be found.

        Arguments:
        method:     A function object of the control-flow-graph
        node_ctr:   Counts the number of nodes in this method and gives them \
                    a unique id.
        bbs:        The basic blocks of the control-flow-graph that have not \
                    yet been added to a CompactNode of any method.
        rbbs:       The basic blocks that have been removed from bbs and \
                    cannot be added to any other CompactNode anymore.

        Outputs:
        bb:         The basic block that will be the start of the next \
                    CompactNode
        bbs:        The basic blocks that have not yet been added to any \
                    CompactNode of any method and can be put into the \
                    CompactNode under creation.
        rbbs:       The basic blocks that have been removed from bbs and \
                    cannot be added to any other CompactNode anymore afte \
                    this function has run.
        """
        for i, bb in enumerate(method.basic_blocks):
            illegal_inc_bbs = [x for x in method.basic_blocks if x not in rbbs]
            bb_not_removed = bb not in rbbs
            bb_is_reachable = not all([x in illegal_inc_bbs for x in
                                       bb.incoming_basic_blocks(method.key)])
            bb_has_no_incoming_blocks = \
                len(bb.incoming_basic_blocks(method.key)) == 0
            if bb_not_removed & (bb_is_reachable | bb_has_no_incoming_blocks):
                bbs.remove(bb)
                rbbs = rbbs + [bb]
                return bb, bbs, rbbs, True
        return None, bbs, rbbs, False

    def Compactify_Basic_Blocks(self, method, cb, bbs, rbbs, Cbbs):
        """
        Identify all basic_blocks that should form a CompactNode together.

        Arguments:
        method: A function object of the control-flow-graph
        cb:     The most recent basic_block that should be added to the \
                CompactNode.
        bbs:    The basic blocks of the control-flow-graph that have not yet \
                been added to a CompactNode.
        rbbs:   The basic blocks of the control-flow-graph that have been \
                removed from bbs because they have been added to a CompactNode.
        Cbbs:   A list of all the basic_blocks that should be added to this \
                CompactNode.
        Outputs:
        bbs:    The basic blocks that have not yet been added to any \
                CompactNode and cannot be put into the CompactNode under \
                creation.
        rbbs:   The basic blocks that have been removed from bbs and cannot \
                be added to any other CompactNode anymore.
        end_pc: The last pc of the newly formed CompactNode.
        Cbbs:   The basic blocks that are a part of this CompactNode.
        outg_bb_startpcs: The start_pc's of all the basic blocks that are \
                          connected by an edge to the end of the CompactNode.
        """
        all_outgoing_bb = list(
            set(item for sublist in cb.outgoing_basic_blocks_as_dict.values()
                for item in sublist))
        if (len(all_outgoing_bb) != 1) | \
                (len(cb.outgoing_basic_blocks(method.key)) != 1):
            end_pc = cb.end.pc
            Cbbs = Cbbs + [cb]
            outg_bb_startpcs = \
                [bb.start.pc for bb in all_outgoing_bb]
            return bbs, rbbs, end_pc, Cbbs, outg_bb_startpcs
        else:
            nbb = cb.outgoing_basic_blocks(method.key)[0]
            all_inc_bb = list(
                set(item for sublist in
                    nbb.incoming_basic_blocks_as_dict.values() for
                    item in sublist))
            if len(all_inc_bb) > 1:
                end_pc = cb.end.pc
                Cbbs = Cbbs + [cb]
                outg_bb_startpcs = [bb.start.pc for bb in
                                    all_outgoing_bb]
                return bbs, rbbs, end_pc, Cbbs, outg_bb_startpcs
            else:
                new_bbs = bbs.copy()
                new_bbs.remove(nbb)
                rbbs = rbbs + [nbb]
                Cbbs = Cbbs + [cb]
                return self.Compactify_Basic_Blocks(
                    method, nbb, new_bbs, rbbs, Cbbs)

    def Merge_Double_Nodes(self, _double_nodes):
        """Merge Compact Nodes that are shared by multiple methods by setting\
        all_node_ids and creating a new node_id whenever necessary."""
        double_nodes = _double_nodes
        ans = []
        node_ctr = 1
        for start_pc in double_nodes.keys():
            if len(double_nodes[start_pc]) == 1:
                # This node is not double
                ans = ans + double_nodes[start_pc]
            else:
                # These nodes are shared
                tempNode = double_nodes[start_pc][0]
                sharedNode = CompactNode(_node_id=("Shared", node_ctr),
                                         _all_node_ids=set(
                                             cNode.node_id for cNode in
                                             double_nodes[start_pc]),
                                         _start_pc=tempNode.start_pc,
                                         _end_pc=tempNode.end_pc,
                                         _basic_blocks=tempNode.basic_blocks,
                                         _inc_node_ids=tempNode.inc_node_ids,
                                         _outg_node_ids=tempNode.outg_node_ids)
                ans = ans + [sharedNode]
                node_ctr += 1
        return ans

    def Add_incoming_outgoing_node_ids(self, compactNodes, simple_edges):
        """
        Add the correct incoming- and outgoing_node_ids to the CompactNodes \
        after identifying all the CompactNodes.

        Arguments:
        compactNodes: The list of all the CompactNodes in this \
                      control-dependency-graph
        simple_edges: A dictionary of edges with starting point denoted by the\
                      corresponding CompactNode_id and end points denoted by \
                      the start_pcs of the corresponding basic_blocks.
        Outputs:
        compactNodes: The CompactNodes in this control-flow-graph with \
                      updated incoming- and outgoing_node_ids.
        """
        for startNode_id in simple_edges.keys():
            for outg_node_startpc in simple_edges[startNode_id]:
                startNode = next((cNode for cNode in compactNodes if
                                  startNode_id in cNode.all_node_ids), None)
                assert startNode is not None, "No startNode was found for a "\
                    f"simple edge from {startNode_id} to {outg_node_startpc}"
                endNode = next((cNode for cNode in
                                compactNodes if cNode.start_pc ==
                                outg_node_startpc), None)

                if endNode.node_id not in startNode.outg_node_ids:
                    startNode.outg_node_ids.append(endNode.node_id)
                    assert startNode.node_id not in endNode.inc_node_ids, \
                        f"{startNode.node_id} doesn't says it's going to "
                    f"{endNode.node_id} but {endNode.node_id} does say "
                    f"{startNode.node_id} is leading into it."  # REMOVE THIS
                    endNode.inc_node_ids.append(startNode.node_id)
        return compactNodes

    def Remove_Invalid_Nodes(self, _compactNodes):
        """Remove nodes that are just typechecks or will never be reached."""
        config = configparser.ConfigParser()
        config.read("./IrrelNodePatterns.ini")
        irrelNodePatterns = eval(config['Patterns']['irrelNodePatterns'])
        typeCheckPatterns = eval(config['Patterns']['typeCheckPatterns'])

        irrelNodes = set()
        irrelNodes_node_ids = set()
        for cNode in _compactNodes:
            if (len(cNode.basic_blocks) == 1) & \
                ([ins.name for ins in cNode.basic_blocks[0].instructions] in
                 irrelNodePatterns):
                irrelNodes.add(cNode)
                irrelNodes_node_ids.add(cNode.node_id)
            elif [re.sub("[0-9]", "", ins.name) for ins in
                  cNode.basic_blocks[-1].instructions] in typeCheckPatterns:
                children = [childNode for childNode in _compactNodes if
                            childNode.node_id in cNode.outg_node_ids]
                for child in children:
                    if [ins.name for ins in
                            child.basic_blocks[0].instructions] == \
                            ["PUSH1", "DUP1", "REVERT"]:
                        irrelNodes.add(child)
                        irrelNodes_node_ids.add(child.node_id)
        relNodes = list(set(_compactNodes) - irrelNodes)
        for irrelNode in irrelNodes:
            irrelNode.show_CompactNode(True)
        for relNode in relNodes:
            assert not bool(
                set(relNode.inc_node_ids).intersection(irrelNodes_node_ids)), \
                "Irrelevant Nodes should not be found among incoming nodes."
            relNode.outg_node_ids = list(set(relNode.outg_node_ids).difference(
                irrelNodes_node_ids))

        return relNodes

    def Find_Compact_Edges_StartPoints(self, cNodes):
        """
        Go through all the CompactNodes in the control-dependency-graph and \
        identify the corresponding CompactEdges.

        Arguments:
        cNodes: The CompactNodes of the control-dependency-graph.

        Outputs:
        E:      The CompactEdges of the control-dependency-graph.
        s:      The startNodes of the control-dependency-graph.
        """
        E = []
        s = set()

        for cNode in cNodes:
            for outg_node_id in cNode.outg_node_ids:
                inc_node_id = cNode.node_id
                E = E + [CompactEdge(inc_node_id, outg_node_id, None)]
                if len(cNode.inc_node_ids) == 0:
                    s.add(cNode)

        return E, s

    def Find_Predicate(self, bb, predicates):
        """
        Find the predicate that controls whether a certain edge is traversed \
        or not by looking at the Opcodes in the last basic_block executed \
        before the Edge could be traveled.

        Arguments:
        bb:         The last basic_block in the node that starts the edge.
        predicates: The relevant Opcodes for the predicates that control
                    branches.

        Outputs:
        eval:       A string describing the predicate that controls whether
                    the Edge is traversed or not.
        pc:         The pc where the eval is present in the deployed bytecode.
        """
        pc = None
        # First we look from front to back for a valid Predicate
        for i, inst in enumerate(bb.instructions):
            if inst.name in predicates:
                if pc is None:
                    eval = inst.name
                    pc = inst.pc
                else:
                    logging.warning("There are multiple predicates inside a "
                                    "single basic block. This could mean some "
                                    "predicates are overlooked.")
                    return eval, pc
        if pc is not None:
            return eval, pc
        # Then we look backwards for ISZERO
        for i, inst in reversed(list(enumerate(bb.instructions))):
            if inst.name == "ISZERO":
                eval = inst.name
                pc = inst.pc
                return eval, pc
        # If neither are found the predicate is NONE
        eval = "NONE"
        pc = bb.start.pc
        return eval, pc

    def LT(self, predicates):
        """Python implementation of the Lengauer-Tarjan algorithm for creating \
        a Control-Dependency-Graph, \
        see https://dl.acm.org/doi/10.1145/357062.357071 ."""
        # Create the spanning Tree using Depth-First-Search

        assert len(self.StartNodes) == 1, "Expected exactly 1 startnode "\
            f"found {len(self.StartNodes)} instead!"
        self.DFS(next(sNode for sNode in self.StartNodes))
        self.n -= 1

        # While creating the CDG a we keep track of a forest which is
        # initialised here. This is the equivalen of LINK.
        forestEdges = set()

        # Find semidominators and initialise immediate dominators
        for i in range(self.n, 0, -1):
            w = self.vertex[i]
            w.label = i
            # Finding semidominators
            for v_id in w.inc_node_ids:
                v = next((compactNode for compactNode in self.CompactNodes if
                          compactNode.node_id == v_id), None)
                assert v is not None, \
                    "No Node was found from the list of incoming nodes!"
                u = self.EVAL(v)
                if u.semi < w.semi:
                    w.semi = u.semi

            # Add w to the bucket of its semidominator
            self.vertex[w.semi].bucket.add(w)
            newEdge = next((cEdge for cEdge in self.CompactEdges if (
                cEdge.startNode_id == w.parent.node_id) &
                (cEdge.endNode_id == w.node_id)), None)
            assert newEdge is not None, \
                "No Edge was found between a node and its parent!"
            forestEdges.add(newEdge)
            w.ancestor = w.parent
            w.label = i

            # Initialise immediate dominators
            parent_bucket = w.parent.bucket.copy()
            for v in parent_bucket:
                w.parent.bucket.remove(v)
                u = self.EVAL(v)

                if u.semi < v.semi:
                    v.dom = u
                else:
                    v.dom = w.parent

        # Finally find immediate dominators not found in previous step
        for w in self.vertex[1:]:
            if w.dom != self.vertex[w.semi]:
                w.dom = w.dom.dom
            # The outgoing_node_ids will be set later on.
            w.outg_node_ids = []

            # Set the predicates of each node
            e, pc = self.Find_Predicate(w.basic_blocks[-1], predicates)
            predicate = Predicate(e, pc, w.node_id)
            w.predicate = predicate

        # Do the same for the root node
        self.vertex[0].dom = None
        self.vertex[0].outg_node_ids = []
        e, pc = self.Find_Predicate(
            self.vertex[0].basic_blocks[-1], predicates)
        assert e != "NONE", "The root node cannot have predicate NONE!"
        predicate = Predicate(e, pc, self.vertex[0].node_id)
        self.vertex[0].predicate = predicate

        # The incoming and outgoing node_ids can be set by using the dom_ids,
        # the edges go from each node to their dominator
        Edges = []
        for i in range(self.n, 0, -1):
            self.vertex[i].inc_node_ids = [self.vertex[i].dom.node_id]
            self.vertex[i].outg_node_ids = [
                cNode.node_id for cNode in
                self.vertex if cNode.dom == self.vertex[i]]
            assert self.vertex[i].dom is not None, \
                "There is a non-root node without an immediate dominator!"
            Edges = Edges + \
                [CompactEdge(self.vertex[i].dom.node_id,
                             self.vertex[i].node_id,
                             self.vertex[i].dom.predicate)]

        self.vertex[0].outg_node_ids = [
            cNode.node_id for cNode in
            self.vertex if cNode.dom == self.vertex[0]]

        for Edge in Edges:
            if (Edge.predicate.eval == "NONE") | \
                    (Edge.predicate.eval == "ISZERO"):
                # Check if the lack of a predicate is a result of a &&- or ||-
                # statement in the code
                pNode = next(cNode for cNode in self.vertex if
                             Edge.startNode_id == cNode.node_id)
                try:
                    ppNode = next(cNode for cNode in self.vertex if
                                  Edge.startNode_id in cNode.outg_node_ids)
                    all_inc_bb = pNode.basic_blocks[0].\
                        all_incoming_basic_blocks
                    if len(all_inc_bb) == 2:
                        # There is another basic block with the predicate
                        predicateNode = next(cNode for cNode in self.vertex if
                                             (cNode.node_id != ppNode.node_id)
                                             & (cNode.basic_blocks[-1] in
                                                all_inc_bb))

                        if (len(predicateNode.outg_node_ids) == 0) & \
                                (predicateNode.predicate.eval != "NONE"):
                            # This is an unused predicate
                            Edge.predicate = predicateNode.predicate
                except:
                    pass

        # The CompactNodes are now equal to self.vertex
        self.CompactNodes = self.vertex

        # The CompactEdges are equal to the edges from the forest
        self.CompactEdges = Edges

    def DFS(self, v):
        """Create a spanning-tree using Depth-First Search."""
        v.semi = self.n
        self.vertex[self.n] = v
        self.n += 1
        for w_id in v.outg_node_ids:
            w = next((compactNode for compactNode in
                      self.CompactNodes if compactNode.node_id == w_id), None)
            if w is None:
                logging.error("This is the node I cannot find children for.")
                v.show_CompactNode(True)
            assert w is not None, "No child node was found!"
            if w.semi == 0:
                w.parent = v
                self.DFS(w)
                assert v.node_id in w.inc_node_ids, \
                    "Something went wrong with the Incoming Node ids!"

    def EVAL(self, _v,):
        """Implement the EVAl function from Lengauer-Tarjan algorithm."""
        if _v.ancestor is None:
            return _v
        else:
            self.COMPRESS(_v)
            return self.vertex[_v.label]

    def COMPRESS(self, _v):
        """COMPRESS function from Lengauer-Tarjan algorithm."""
        if _v.ancestor.ancestor is not None:
            self.COMPRESS(_v.ancestor)
            if self.vertex[_v.ancestor.label].semi < \
                    self.vertex[_v.label].semi:
                _v.label = _v.ancestor.label
            _v.ancestor = _v.ancestor.ancestor

    def Show_CDG(self, log=False):
        """Show all CompactNodes and Edges in the Control-Dependency-Graph."""
        if log:
            logging.info("Nodes:")
            for cNode in self.CompactNodes:
                cNode.show_CompactNode(True)
            logging.info("Edges:")
            for cEdge in self.CompactEdges:
                cEdge.show_CompactEdge(True)
        else:
            print("Nodes:")
            for cNode in self.CompactNodes:
                cNode.show_CompactNode()
            print("Edges:")
            for cEdge in self.CompactEdges:
                cEdge.show_CompactEdge()
