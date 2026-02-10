# 3. UI Navigation & Feature Map

Date: 2026-01-11

## Status

Proposed

## Context

The updated requirements specify a 4-tab structure for the main interface and a distinct onboarding flow for Identity and Agent configuration. Users only communicate with their own Agent, but can view their Agent's external interactions.

## Decision

We will implement a **Single Activity** application with **Jetpack Compose Navigation**.

### Onboarding Flow (First Run)
1.  **Welcome / Registration**: Input Email & Research Field.
2.  **Agent Configuration**: Input LLM Base URL & API Key.
    - *Security*: API Key stored in `EncryptedSharedPreferences`.
3.  **Identity Generation**: Generate RSA/ECC KeyPair.
    - *Security*: Private Key generated in Android Keystore (non-exportable).
    - *Output*: Public Key (Wallet Address).

### Main Navigation (Bottom Bar)

1.  **Messages (消息)**
    - **Private Chat**: User <-> Agent (Instruction/Feedback).
    - **Public Logs**: Feed of Agent <-> External Network (Read-only observation of what the agent is doing).
    
2.  **Contacts (通讯录)**
    - List of discovered Peers/Nodes.
    - List of Groups (Clusters/Layers).

3.  **Archives (存档)**
    - **Bulletin**: Community Rules/Proposals.
    - **Chain Explorer**: View of the local blockchain ledger.

4.  **Profile (其它)**
    - **Identity**: Show Public Key / QR Code.
    - **Wallet**: Stater Balance, Transaction History.
    - **Settings**: Edit API Keys, Backup Data.

## Consequences

- **Pros**: Clear separation of concerns; User has full visibility of Agent actions without direct manual intervention in P2P.
- **Cons**: "Agent Logs" view needs efficient filtering to avoid overwhelming the user with raw P2P debug logs.
