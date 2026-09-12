"""One unattended graph from raw provider parts through reviewed motion."""

from __future__ import annotations

from gnode import BindingTable, Graph, GraphBuilder, seal_graph
from stage_gen.components.character_3d.io import canonical_digest
from stage_gen.recipes.character_3d.rig_runner import RigRun
from stage_gen.recipes.character_3d.runner import CharacterRun


class FullRun(RigRun):
    def build_graph(self) -> Graph:
        assembly = CharacterRun.build_graph(self)
        binding = self.agent_binding()
        builder = GraphBuilder(
            profile=BindingTable((binding, *self.extra_bindings())), local_max_in_flight=1
        )
        for node in assembly.nodes:
            builder.add(
                self.registry.node_type(node.type_id),
                node.node_id,
                domain=node.domain,
                description=node.description,
                params=node.params,
                depends_on=node.depends_on,
                input_digests=node.input_sha256,
                ports=node.ports,
                duration_seconds=node.estimated_duration_seconds,
            )
        self.add_rig_nodes(
            builder,
            (assembly.graph_sha256, canonical_digest(self.experiment)),
            prior=("assembly_admit",),
        )
        graph = seal_graph(
            Graph,
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id="rig_admit",
            schema_version=1,
            kind="contained-character-parts-to-rig-v1",
        )
        self.registry.validate_graph_types(graph.nodes)
        return graph
