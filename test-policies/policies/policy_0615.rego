package governance.monitoring.action.verify.data.policy_0615

# Auto-generated policy 615
# Package: governance.monitoring.action.verify.data

# Metadata
metadata := {
    "policy_id": "0615",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0615 {
    input.user.active
    input.resource.public
}
allowed_0615 {
    input.user.role == "admin"
}

# Utility function for user info
