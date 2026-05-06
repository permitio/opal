package risk.enforcement.action.allow.policy_0656

# Auto-generated policy 656 (Rego v1 syntax)
# Package: risk.enforcement.action.allow

# Metadata
metadata := {
    "policy_id": "0656",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0656_allowed = false
policy_0656_allowed if {
    input.user.active
    input.resource.public
}
