package security.enforcement.user.allow.data.policy_0516

# Auto-generated policy 516 (Rego v1 syntax)
# Package: security.enforcement.user.allow.data

# Metadata
metadata := {
    "policy_id": "0516",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0516_allowed if {
    input.user.role == "admin"
}
policy_0516_allowed if {
    input.user.active
    input.resource.public
}
