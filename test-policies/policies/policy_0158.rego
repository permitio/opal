package risk.authorization.resource.allow.policy_0158

# Auto-generated policy 158 (Rego v1 syntax)
# Package: risk.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0158",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0158_allowed = false
policy_0158_allowed if {
    input.user.role == "admin"
}
policy_0158_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
