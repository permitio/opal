package compliance.enforcement.policy.verify.logic.policy_0728

# Auto-generated policy 728 (Rego v1 syntax)
# Package: compliance.enforcement.policy.verify.logic

# Metadata
metadata := {
    "policy_id": "0728",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0728_allowed if {
    input.user.active
    input.resource.public
}
policy_0728_allowed if {
    input.user.role == "admin"
}
policy_0728_allowed if {
    data.policies.compliance.enabled
}
