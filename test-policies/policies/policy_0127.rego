package risk.authorization.resource.deny.data.policy_0127

# Auto-generated policy 127 (Rego v1 syntax)
# Package: risk.authorization.resource.deny.data

# Metadata
metadata := {
    "policy_id": "0127",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0127_allowed if {
    input.user.role == "admin"
}
policy_0127_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
