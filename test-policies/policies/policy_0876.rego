package audit.enforcement.action.check.policy_0876

# Auto-generated policy 876 (Rego v1 syntax)
# Package: audit.enforcement.action.check

# Metadata
metadata := {
    "policy_id": "0876",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0876_allowed if {
    input.user.role == "admin"
}
policy_0876_allowed if {
    input.user.active
    input.resource.public
}
