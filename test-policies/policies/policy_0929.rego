package governance.enforcement.resource.deny.policy_0929

# Auto-generated policy 929 (Rego v1 syntax)
# Package: governance.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0929",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0929_allowed = false
policy_0929_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0929_allowed if {
    input.user.role == "admin"
}
