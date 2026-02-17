# Organization Join Process - Documentation Index

This directory contains comprehensive documentation for the organization onboarding process across all three components of the NuNet system.

## Documentation Structure

### Component-Specific Documentation

1. **[Appliance Documentation](README.md)** (This Repository)
   - Complete appliance-side onboarding flow
   - Frontend and backend interactions
   - State management and local processing
   - Location: `appliance/org-join-process/`

2. **[Organization Manager Documentation](../../organization_manager/org-join-process/README.md)**
   - Central coordination service
   - Request lifecycle management
   - Worker coordination and round-robin distribution
   - Email verification workflow
   - Location: `organization_manager/org-join-process/`

3. **[Onboarding Worker Documentation](../../onboarding-worker/org-join-process/README.md)**
   - Background processing service
   - Capability token generation
   - Certificate and key generation
   - Contract creation
   - Location: `onboarding-worker/org-join-process/`

### End-to-End Documentation

4. **[End-to-End Solution Documentation](END_TO_END_SOLUTION.md)**
   - Complete system architecture
   - All component interactions
   - Data flow and state synchronization
   - Security model and scalability considerations
   - Location: `appliance/org-join-process/END_TO_END_SOLUTION.md`

## Visual Diagrams

Each component has a set of Mermaid diagrams:

### Appliance Diagrams
- `01-state-machine.mmd` - State machine for appliance onboarding flow
- `02-sequence-diagram.mmd` - Sequence of interactions
- `03-process-flowchart.mmd` - Complete decision tree
- `04-component-interaction.mmd` - Architecture overview
- `05-end-to-end-sequence.mmd` - Complete end-to-end sequence

### Organization Manager Diagrams
- `01-state-machine.mmd` - Request status lifecycle
- `02-sequence-diagram.mmd` - Interactions with appliances and workers
- `03-process-flowchart.mmd` - Complete decision tree
- `04-component-interaction.mmd` - Architecture overview

### Onboarding Worker Diagrams
- `01-state-machine.mmd` - Worker processing states
- `02-sequence-diagram.mmd` - Worker interactions
- `03-process-flowchart.mmd` - Complete decision tree
- `04-component-interaction.mmd` - Architecture overview

## Quick Start Guide

### For Developers

1. **Understanding the Appliance Side**: Start with [Appliance Documentation](README.md)
2. **Understanding the Backend**: Read [Organization Manager Documentation](../../organization_manager/org-join-process/README.md)
3. **Understanding Workers**: Read [Onboarding Worker Documentation](../../onboarding-worker/org-join-process/README.md)
4. **Understanding the Big Picture**: Read [End-to-End Solution Documentation](END_TO_END_SOLUTION.md)

### For System Architects

1. Start with [End-to-End Solution Documentation](END_TO_END_SOLUTION.md) for system overview
2. Review component-specific documentation for implementation details
3. Examine Mermaid diagrams for visual understanding

### For Operations

1. Review [End-to-End Solution Documentation](END_TO_END_SOLUTION.md) for deployment architecture
2. Check component-specific documentation for configuration requirements
3. Review error handling sections in each component's documentation

## Key Concepts

### Request Lifecycle

1. **Submission**: Appliance submits request to Organization Manager
2. **Verification**: Email verification via Organization Manager
3. **Processing**: Worker claims and processes request
4. **Completion**: Worker submits results, Appliance retrieves and applies

### State Synchronization

- **Appliance**: Local state file (`~/.nunet/appliance/onboarding_state.json`)
- **Organization Manager**: Database (`OnboardingRequest` model)
- **Worker**: Stateless (no persistent state)

### Security Model

- **Appliance → Organization Manager**: Public endpoints, `status_token` for polling
- **Worker → Organization Manager**: API key authentication
- **Secrets**: Managed via OpenBao (workers) or local config (appliance)

## Related Documentation

- [Appliance README](../../README.md)
- [Organization Manager README](../../organization_manager/README.md)
- [Onboarding Worker README](../../onboarding-worker/README.md)

## Contributing

When updating the onboarding process:

1. Update the relevant component documentation
2. Update the end-to-end documentation if cross-component changes
3. Update Mermaid diagrams if flow changes
4. Keep all documentation in sync

## Diagram Generation

To generate SVG diagrams from Mermaid files, use the provided conversion scripts:

```bash
# In appliance/org-join-process/
./convert-mermaid.sh

# Or use Python script
python convert-mermaid.py
```

See [README-CONVERSION.md](README-CONVERSION.md) for details.
