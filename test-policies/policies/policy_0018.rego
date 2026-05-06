package audit.validation.policy.check.policy_0018

# Auto-generated policy 18 (Rego v1 syntax)
# Package: audit.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0018",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0018_allowed if {
    input.user.active
    input.resource.public
}
policy_0018_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
