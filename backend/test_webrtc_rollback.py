import asyncio

from aiortc import RTCPeerConnection, RTCSessionDescription


async def test_rollback():
    pc = RTCPeerConnection()
    try:
        print(f"Initial state: {pc.signalingState}")

        # Create an offer to move state to have-local-offer
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        print(f"State after local offer: {pc.signalingState}")

        # Try rollback
        print("Attempting rollback...")
        rollback = RTCSessionDescription(sdp="", type="rollback")
        await pc.setLocalDescription(rollback)
        print(f"State after rollback: {pc.signalingState}")

        if pc.signalingState == "stable":
            print("Rollback SUCCESSFUL")
        else:
            print(f"Rollback FAILED: State is {pc.signalingState}")

    except Exception as e:
        print(f"Error during rollback test: {e}")
    finally:
        await pc.close()


if __name__ == "__main__":
    asyncio.run(test_rollback())
