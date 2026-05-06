package compliance.validation.resource.check.policy_0325

# Auto-generated policy 325 (Rego v1 syntax)
# Package: compliance.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0325",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0325_allowed if {
    data.policies.compliance.enabled
}
default policy_0325_allowed = false
policy_0325_allowed if {
    input.user.role == "admin"
}
policy_0325_allowed if {
    input.user.active
    input.resource.public
}
