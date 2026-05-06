package governance.authentication.user.verify.policy_0979

# Auto-generated policy 979 (Rego v1 syntax)
# Package: governance.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0979",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0979_allowed if {
    input.user.active
    input.resource.public
}
policy_0979_allowed if {
    input.user.role == "admin"
}
default policy_0979_allowed = false
policy_0979_allowed if {
    data.policies.governance.enabled
}
