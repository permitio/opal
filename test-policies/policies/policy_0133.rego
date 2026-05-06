package risk.enforcement.context.deny.policy_0133

# Auto-generated policy 133 (Rego v1 syntax)
# Package: risk.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0133",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0133_allowed = false
policy_0133_allowed if {
    input.user.active
    input.resource.public
}
policy_0133_allowed if {
    input.user.role == "admin"
}
