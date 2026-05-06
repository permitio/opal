package compliance.enforcement.user.check.policy_0144

# Auto-generated policy 144 (Rego v1 syntax)
# Package: compliance.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0144",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0144_allowed if {
    input.user.role == "admin"
}
policy_0144_allowed if {
    input.user.active
    input.resource.public
}
policy_0144_allowed if {
    data.policies.compliance.enabled
}
default policy_0144_allowed = false
