import asyncio
import json
from backend.app.p2p_community import Node, NetworkManager
from backend.app.p2p_community.protocol import MSG_DIRECT, MSG_GROUP

async def main():
    print("=== P2P Community Simulation Start ===")
    
    # 1. Initialize Network
    # Small capacity to force hierarchy growth quickly for demonstration
    manager = NetworkManager(max_subgroups=2, group_capacity=3)
    
    # 2. Add Nodes
    nodes = []
    print("\n--- Adding Nodes & Forming Hierarchy ---")
    for i in range(15):
        node = Node(f"node_{i}", manager)
        manager.register_node(node)
        nodes.append(node)
        await asyncio.sleep(0.1) # Simulate time gap

    # 3. Inspect Structure
    print("\n--- Network Structure ---")
    structure = manager.get_network_structure()
    print(json.dumps(structure, indent=2))
    
    # 4. Simulate Communication
    print("\n--- Testing Communication ---")
    
    # Case A: Direct Message (Node 0 -> Node 5)
    # Node 0 is likely in a different group than Node 5
    print("\n[Test] Direct Message:")
    await nodes[0].send_message(target_id=nodes[5].node_id, content="Hello Friend!", msg_type=MSG_DIRECT)
    
    # Case B: Group Broadcast
    # Node 0 sends to its own group
    # We need to find which group Node 0 is in
    group_id = list(nodes[0].group_ids)[0]
    print(f"\n[Test] Group Broadcast to {group_id}:")
    await nodes[0].send_message(target_id=group_id, content=f"Hello Group {group_id}!", msg_type=MSG_GROUP)
    
    # Give async tasks a moment to complete
    await asyncio.sleep(1)
    
    print("\n=== Simulation End ===")

if __name__ == "__main__":
    asyncio.run(main())
