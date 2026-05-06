package compliance.authentication.policy.verify.policy_0723

# Auto-generated policy 723 (Rego v1 syntax)
# Package: compliance.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0723",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0723_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0723_allowed if {
    data.policies.compliance.enabled
}
policy_0723_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0723_allowed if {
    input.user.active
    input.resource.public
}
