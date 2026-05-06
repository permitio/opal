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
policy_0615_allowed if {
    input.user.active
    input.resource.public
}
policy_0615_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
