package access.authorization.context.deny.policy_0311

# Auto-generated policy 311 (Rego v1 syntax)
# Package: access.authorization.context.deny

# Metadata
metadata := {
    "policy_id": "0311",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0311_allowed if {
    input.user.role == "admin"
}
policy_0311_allowed if {
    data.policies.access.enabled
}
policy_0311_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
