package access.enforcement.resource.deny.policy_1000

# Auto-generated policy 1000 (Rego v1 syntax)
# Package: access.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "1000",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_1000_allowed if {
    input.user.role == "admin"
}
policy_1000_allowed if {
    input.user.active
    input.resource.public
}
