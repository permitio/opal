package compliance.authentication.context.check.policy_0200

# Auto-generated policy 200 (Rego v1 syntax)
# Package: compliance.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0200",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0200_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0200_allowed = false
policy_0200_allowed if {
    input.user.active
    input.resource.public
}
policy_0200_allowed if {
    data.policies.compliance.enabled
}
