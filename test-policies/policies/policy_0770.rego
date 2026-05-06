package compliance.validation.policy.verify.policy_0770

# Auto-generated policy 770 (Rego v1 syntax)
# Package: compliance.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0770",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0770_allowed if {
    input.user.active
    input.resource.public
}
policy_0770_allowed if {
    data.policies.compliance.enabled
}
policy_0770_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
