package compliance.validation.context.check.policy_0812

# Auto-generated policy 812 (Rego v1 syntax)
# Package: compliance.validation.context.check

# Metadata
metadata := {
    "policy_id": "0812",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0812_allowed if {
    data.policies.compliance.enabled
}
policy_0812_allowed if {
    input.user.role == "admin"
}
default policy_0812_allowed = false
policy_0812_allowed if {
    input.user.active
    input.resource.public
}
