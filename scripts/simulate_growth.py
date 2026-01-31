"""
Network Growth Simulation Script

Simulates the growth of the P2P network from 1 to 100 nodes.
Configuration:
- Group Capacity: 10
- Max Subgroups: 10

Scenario:
1. Nodes join the network one by one.
2. They are assigned to Level 1 groups.
3. When a Level 1 group fills up (10 nodes), a Representative is elected.
4. The Representative joins the Level 2 Group (Parent/Root).
5. Level 2 Group is the parent of all Level 1 groups.
"""
import asyncio
import logging
import uuid
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.p2p_community.bootstrap_client import LocalBootstrapSimulator, NodeRegistration, GroupInfo

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler("simulation_log.txt", mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Simulation")

async def run_simulation():
    logger.info("=== Starting Network Growth Simulation (1 -> 100 Nodes) ===")
    
    # 1. Initialize Bootstrap with Config
    # Capacity 10, Max Subgroups 10
    bootstrap = LocalBootstrapSimulator(group_capacity=10, max_subgroups=10)
    
    # Identify the Root Group (our Level 2 group in User's terminology)
    # Simulator creates a Root (Level 0) and first Child (Level 1)
    topo = await bootstrap.get_network_topology()
    groups = topo['groups']
    
    root_group = None
    level_1_groups = []
    
    for gid, g in groups.items():
        if g['level'] == 0:
            root_group = g
        elif g['level'] == 1:
            level_1_groups.append(g)
            
    logger.info(f"Initialized Network. Root Group (Level 2): {root_group['group_id']}")
    logger.info(f"Initial Level 1 Group: {level_1_groups[0]['group_id']}")
    
    # Track nodes
    nodes = [] # List of dicts
    
    # 2. Add 100 Nodes
    for i in range(1, 101):
        node_name = f"Node_{i:03d}"
        
        # Determine Node Public Key (Simulated)
        # Use a deterministic UUID based on name for stability
        # But in models we use UUIDv5(pk). Here let's just create a key.
        # Actually Bootstrap requires (id, pk, ip, port).
        # We'll generate a random key.
        # Wait, previous refactor: ID is UUID.
        # We'll use a random UUID for ID, and random string for PK.
        
        pk = f"pk_{node_name}"
        node_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, node_name))
        
        # Register
        logger.info(f"--- Adding {node_name} ({node_id[:8]}) ---")
        
        # Logic: New node joins Level 1
        # Get joinable groups
        joinable = await bootstrap.get_joinable_groups(preferred_level=1)
        
        target_group_id = None
        if joinable:
            target_group_id = joinable[0].group_id
        else:
            logger.error("No joinable groups available! Capacity reached?")
            break
            
        reg = NodeRegistration(
            node_id=node_id,
            public_key=pk,
            ip_address="127.0.0.1",
            port=8000 + i,
            group_id=target_group_id
        )
        
        success = await bootstrap.register_node(reg)
        if success:
            logger.info(f"{node_name} joined Group {target_group_id}")
            nodes.append({"id": node_id, "name": node_name, "pk": pk, "group": target_group_id})
            
            # Check if group is now full (Elect Representative)
            # Fetch group info
            topo = await bootstrap.get_network_topology()
            group_info = topo['groups'][target_group_id]
            
            if group_info['member_count'] == 10:
                logger.info(f"Group {target_group_id} is FULL (10 members). Electing Representative...")
                
                # Simple Election: The last joined node (or random) becomes Rep
                # Let's say Node_X is elected.
                rep_node = nodes[-1] 
                
                logger.info(f"Elected {rep_node['name']} as Representative for Group {target_group_id}")
                
                # Check constraints: Node can be in 2 groups? Yes.
                # Rep joins Root Group (Level 0)
                # Registering to a second group requires modifying internal state in simulator 
                # because register_node() usually handles *new* nodes or initial assignment.
                # But we can call register_node with a different group?
                # Simulator register_node implementation:
                # if group_id: peers[id] exists? yes. add to group members.
                # So we can just call register_node again with the root ID.
                
                reg_rep = NodeRegistration(
                    node_id=rep_node['id'],
                    public_key=rep_node['pk'],
                    ip_address="127.0.0.1",
                    port=8000 + i,
                    group_id=root_group['group_id']
                )
                
                success_rep = await bootstrap.register_node(reg_rep)
                if success_rep:
                    logger.info(f"Representative {rep_node['name']} joined Parent Group {root_group['group_id']}")
                else:
                    logger.error(f"Failed to add Representative to Parent Group")

        else:
            logger.error(f"Failed to register {node_name}")
            
    # 3. Final Report
    logger.info("=== Simulation Complete ===")
    topo = await bootstrap.get_network_topology()
    
    total_nodes = topo['total_nodes']
    groups = topo['groups']
    
    logger.info(f"Total Nodes: {total_nodes}")
    logger.info(f"Total Groups: {len(groups)}")
    
    # Print Hierarchy
    # Root
    r = groups[root_group['group_id']]
    logger.info(f"\n[Level 2 (Root)] {r['group_id']} | Members: {r['member_count']}")
    
    # Children
    sorted_groups = sorted([g for g in groups.values() if g['level'] == 1], key=lambda x: x['group_id'])
    for g in sorted_groups:
        logger.info(f"  └── [Level 1] {g['group_id']} | Members: {g['member_count']}")

if __name__ == "__main__":
    asyncio.run(run_simulation())
