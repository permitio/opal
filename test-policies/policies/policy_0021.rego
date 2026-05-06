package governance.authentication.policy.allow.policy_0021

# Auto-generated policy 21 (Rego v1 syntax)
# Package: governance.authentication.policy.allow

# Metadata
metadata := {
    "policy_id": "0021",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0021_allowed if {
    input.user.role == "admin"
}
policy_0021_allowed if {
    input.user.active
    input.resource.public
}
